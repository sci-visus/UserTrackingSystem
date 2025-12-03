import panel as pn
import param
import openslide
from panel.reactive import ReactiveHTML
from PIL import Image
import logging
import os
import json
import glob
import time
from datetime import datetime
from dotenv import load_dotenv
from redis_cache import cache
from keyboard_shortcuts import KeyboardShortcutManager
from settings_modal import create_settings_button_and_modal
from auth_middleware import auth_manager
from redis_helper import redis_helper


cache_key="annotation_tool_cache_v1"


# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get port configuration from environment variables
DZI_SERVER_PORT = os.getenv('DZI_SERVER_PORT', '10566')

# Initialize Panel extension - load JS/CSS globally
pn.extension(sizing_mode="stretch_width", 
             css_files=[
                 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.css'
             ], 
             js_files={
                 'leaflet': 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.js'
             })

def load_metadata(metadata_path):
    """Load viewer metadata from JSON file generated during DZI conversion"""
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            logger.info(f"✓ Loaded metadata from {metadata_path}")
            logger.info(f"  Image dimensions: {metadata['original_dimensions']['width']}x{metadata['original_dimensions']['height']}")
            logger.info(f"  Aspect ratio: {metadata['aspect_ratio']}")
            logger.info(f"  Recommended start level: {metadata['recommended_start_level']}")
            logger.info(f"  Center offset Y: {metadata['center_offset_y']}")
            return metadata
    else:
        logger.warning(f"⚠ Metadata file not found: {metadata_path}")
        logger.warning("Using default values. Run convert_to_dzi.py to generate metadata.")
        return {
            "recommended_start_level": 8,
            "center_offset_y": -1.15,
            "dzi_levels": 18
        }


def load_scalebar_metadata(image_name):
    """Load scalebar metadata (mpp_x) for an image from svs_metadata directory"""
    metadata_path = f"/data/svs_metadata/{image_name}_svs_scalebar_metadata.json"

    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                scalebar_data = json.load(f)
                mpp_x = scalebar_data.get('mpp_x', None)  # microns per pixel
                
                if mpp_x is not None:
                    # Convert to float if it's a string
                    try:
                        mpp_x_float = float(mpp_x)
                    except (ValueError, TypeError) as e:
                        logger.error(f"mpp_x value '{mpp_x}' is not a valid number: {e}")
                        logger.info("Using default mm_per_pixel: 0.0004")
                        return 0.0004
                    
                    # Convert from microns per pixel to mm per pixel
                    # 1 micron = 0.001 mm
                    mm_per_pixel = mpp_x_float * 0.001
                    print(f"✓ Loaded scalebar metadata: mpp_x={mpp_x_float} µm/px → {mm_per_pixel} mm/px")
                    logger.info(f"✓ Loaded scalebar metadata: mpp_x={mpp_x_float} µm/px → {mm_per_pixel} mm/px")
                    return mm_per_pixel
                else:
                    logger.warning(f"⚠ mpp_x not found in {metadata_path}")
        except Exception as e:
            logger.error(f"Error loading scalebar metadata from {metadata_path}: {e}")
    else:
        logger.warning(f"⚠ Scalebar metadata file not found: {metadata_path}")
    
    # Default fallback: 0.0005 mm/px (0.5 µm/px = 40x magnification)
    logger.info("Using default mm_per_pixel: 0.0004")
    return 0.0004

def ensure_annotation_directories(image_name):
    """Ensure annotation directories exist with proper permissions for an image"""
    base_dir = "/data/anno"
    image_dir = os.path.join(base_dir, image_name)
    live_dir = os.path.join(image_dir, "live_tracking")
    saved_dir = os.path.join(image_dir, "saved_views")
    
    # Create directories if they don't exist
    for directory in [base_dir, image_dir, live_dir, saved_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory, mode=0o777)
            logger.info(f"Created directory: {directory}")
        # Ensure permissions are set correctly
        os.chmod(directory, 0o777)
    
    return live_dir, saved_dir

def save_annotation_json(filepath, data):
    """Save annotation data to JSON file with proper permissions"""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    os.chmod(filepath, 0o666)  # rw-rw-rw-
    logger.info(f"Saved annotation: {filepath}")

def load_annotation_json(filepath):
    """Load annotation data from JSON file"""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def get_next_live_tracking_number(live_dir):
    """Get the next number for live tracking file"""
    existing_files = glob.glob(os.path.join(live_dir, "*.json"))
    if not existing_files:
        return 0
    
    numbers = []
    for f in existing_files:
        basename = os.path.basename(f)
        try:
            num = int(basename.replace('.json', ''))
            numbers.append(num)
        except ValueError:
            continue
    
    return max(numbers) + 1 if numbers else 0

def cleanup_old_live_tracking(live_dir, max_files=3000):
    """Remove oldest live tracking files if count exceeds max_files"""
    existing_files = glob.glob(os.path.join(live_dir, "*.json"))
    if len(existing_files) <= max_files:
        return
    
    # Sort by number (filename)
    files_with_nums = []
    for f in existing_files:
        basename = os.path.basename(f)
        try:
            num = int(basename.replace('.json', ''))
            files_with_nums.append((num, f))
        except ValueError:
            continue
    
    files_with_nums.sort(key=lambda x: x[0])
    
    # Remove oldest files
    num_to_remove = len(files_with_nums) - max_files
    for i in range(num_to_remove):
        os.remove(files_with_nums[i][1])
        logger.info(f"Removed old live tracking file: {files_with_nums[i][1]}")

def get_saved_views_list(saved_dir):
    """Get list of saved view files sorted by number"""
    existing_files = glob.glob(os.path.join(saved_dir, "*.json"))
    
    files_with_nums = []
    for f in existing_files:
        basename = os.path.basename(f)
        try:
            num = int(basename.replace('.json', ''))
            files_with_nums.append((num, f))
        except ValueError:
            continue
    
    files_with_nums.sort(key=lambda x: x[0])
    return files_with_nums

def load_image_mapping():
    """Load the JSON mapping file"""
    json_path = '/data/tiles_directory_list.json'
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading tiles directory mapping: {e}")
        return []

def get_available_images():
    """Get list of available DZI images from JSON mapping"""
    image_mapping = load_image_mapping()
    
    if not image_mapping:
        logger.warning("No image mapping loaded, falling back to directory scan")
        return get_available_images_from_dir()
    
    images = []
    for entry in image_mapping:
        svs_file = entry.get('svs_file', '')
        tiles_dir = entry.get('tiles_directory', '')
        collection = entry.get('collection_name', '')
        entry_num = entry.get('entry_number', 0)
        
        # Extract base name without .svs extension
        base_name = svs_file.replace('.svs', '')
        
        # Map host paths to container paths
        if '/BRACS/' in tiles_dir:
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/BRACS/BRACS_WSI', '/data/dzi_datasets/BRACS')
        elif '/TCGA-BRCA/' in tiles_dir:
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/TCGA-BRCA/tissue_slides', '/data/dzi_datasets/TCGA')
        elif '/BACH/' in tiles_dir:
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/BACH/ICIAR2018_BACH_Challenge/ICIAR2018_BACH_Challenge/WSI', '/data/dzi_datasets/BACH')
        else:
            container_tiles_dir = tiles_dir
        
        # tiles_directory is the _files folder, parent has .dzi file
        dzi_parent = os.path.dirname(container_tiles_dir)
        dzi_file = os.path.join(dzi_parent, base_name + '.dzi')
        
        if os.path.exists(container_tiles_dir):
            # Look for metadata file
            metadata_path = os.path.join(dzi_parent, f"{base_name}_metadata.json")
            metadata = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except:
                    pass
            
            images.append({
                'name': base_name,
                'display_name': f"[{entry_num}] {base_name[:50]}...\" if len(base_name) > 50 else f\"[{entry_num}] {base_name}",
                'svs_path': f"/data/{svs_file}",
                'dzi_path': dzi_file,
                'tiles_directory': container_tiles_dir,
                'metadata_path': metadata_path,
                'collection': collection,
                'entry_number': entry_num,
                'dimensions': metadata.get('original_dimensions', {}),
                'aspect_ratio': metadata.get('aspect_ratio', 0)
            })
        else:
            logger.debug(f"Tiles not found: {container_tiles_dir}")
    
    logger.info(f"Loaded {len(images)} images from JSON mapping")
    return sorted(images, key=lambda x: x.get('entry_number', 0))

def get_available_images_from_dir():
    """Fallback: Get images from directory scan (old method)"""
    dzi_dir = "/data/dzi_datasets/BACH"
    if not os.path.exists(dzi_dir):
        return []
    
    images = []
    for file in os.listdir(dzi_dir):
        if file.endswith('.dzi'):
            base_name = file.replace('.dzi', '')
            svs_path = f"/data/{base_name}.svs"
            metadata_path = f"{dzi_dir}/{base_name}_metadata.json"
            
            metadata = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading metadata: {e}")
            
            images.append({
                'name': base_name,
                'display_name': base_name[:50] + '...' if len(base_name) > 50 else base_name,
                'svs_path': svs_path,
                'dzi_path': f"{dzi_dir}/{file}",
                'metadata_path': metadata_path,
                'dimensions': metadata.get('original_dimensions', {}),
                'aspect_ratio': metadata.get('aspect_ratio', 0)
            })
    
    return sorted(images, key=lambda x: x['name'])

def ensure_ink_status_directory():
    """Ensure ink status directory exists with proper permissions"""
    ink_status_dir = "/data/ink_status"
    if not os.path.exists(ink_status_dir):
        os.makedirs(ink_status_dir, mode=0o777)
        logger.info(f"Created ink status directory: {ink_status_dir}")
    os.chmod(ink_status_dir, 0o777)
    return ink_status_dir

def load_ink_status(image_name):
    """Load ink status for an image from consolidated JSON file"""
    ink_status_dir = ensure_ink_status_directory()
    status_file = os.path.join(ink_status_dir, "ink_status.json")
    
    # Load all statuses
    all_statuses = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                all_statuses = json.load(f)
        except Exception as e:
            logger.error(f"Error loading ink status file: {e}")
    
    # Return status for this image or default
    if image_name in all_statuses:
        return all_statuses[image_name]
    
    return {
        'done': False,
        'ink_found': False,
        'last_updated': datetime.now().isoformat()
    }

def save_ink_status(image_name, done=False, ink_found=False):
    """Save ink status for an image to consolidated JSON file with proper permissions"""
    ink_status_dir = ensure_ink_status_directory()
    status_file = os.path.join(ink_status_dir, "ink_status.json")
    
    # Load existing statuses
    all_statuses = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                all_statuses = json.load(f)
        except Exception as e:
            logger.error(f"Error loading existing ink status: {e}")
    
    # Update status for this image
    all_statuses[image_name] = {
        'done': done,
        'ink_found': ink_found,
        'last_updated': datetime.now().isoformat()
    }
    
    try:
        with open(status_file, 'w') as f:
            json.dump(all_statuses, f, indent=2)
        os.chmod(status_file, 0o666)  # rw-rw-rw-
        logger.info(f"✓ Saved ink status for {image_name}: done={done}, ink_found={ink_found}")
        return all_statuses[image_name]
    except Exception as e:
        logger.error(f"Error saving ink status: {e}")
        return None

def get_status_counts():
    """Get counts of done and ink_found images from consolidated status file"""
    ink_status_dir = ensure_ink_status_directory()
    status_file = os.path.join(ink_status_dir, "ink_status.json")
    
    done_count = 0
    ink_found_count = 0
    
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                all_statuses = json.load(f)
                for image_name, status in all_statuses.items():
                    if status.get('done', False):
                        done_count += 1
                    if status.get('ink_found', False):
                        ink_found_count += 1
        except Exception as e:
            logger.error(f"Error reading status counts: {e}")
    
    return done_count, ink_found_count


class SVSLeafletViewer(ReactiveHTML):
    """
    Interactive SVS viewer using Leaflet for smooth pan and zoom.
    Uses Leaflet-DeepZoom to display DZI tiles.
    """
    
    dzi_url = param.String(default='', doc="URL to DZI descriptor file")
    
    max_zoom = param.Integer(default=17, doc="Maximum zoom level")
    
    width_px = param.Integer(default=1000, doc="Image width in pixels")
    
    height_px = param.Integer(default=1000, doc="Image height in pixels")
    
    zoom = param.Integer(default=0, bounds=(0, 10), doc="Current zoom level")
    
    zoom_level = param.String(default="Level 3 (1x)", doc="Current zoom level display")

    center = param.List(default=[0, 0], doc="Current center of the map [lat, lng]")
    
    level_dimensions = param.List(default=[], doc="List of [width, height] for each pyramid level")
    
    # Metadata-driven parameters for automatic configuration
    start_level = param.Integer(default=11, doc="DZI level to use as Leaflet zoom 0")
    
    center_offset_y = param.Number(default=-1.12, doc="Y center adjustment multiplier")
    
    # DZI server port configuration
    dzi_server_port = param.String(default='10566', doc="Port for DZI tile server")
    
    # Force re-render trigger
    reload_counter = param.Integer(default=0, doc="Increment to force map reload")

    # Scalebar configuration
    mm_per_pixel = param.Number(default=0.0004, doc="Millimeters per pixel at base resolution")
    
    # SVS metadata for accurate magnification display
    objective_power = param.Number(default=40.0, doc="Base magnification from SVS metadata")
    level_downsamples = param.List(default=[1.0, 4.0, 16.0, 32.0], doc="Downsample factors from SVS metadata")
    
    # Annotation saving/loading parameters
    image_name = param.String(default='', doc="Current image name for annotation storage")
    save_annotation_trigger = param.Integer(default=0, doc="Trigger to save current annotations")
    load_annotation_trigger = param.Integer(default=0, doc="Trigger to load annotations")
    annotation_data = param.String(default='', doc="JSON string of annotations to load")
    undo_trigger = param.Integer(default=0, doc="Trigger undo operation")
    redo_trigger = param.Integer(default=0, doc="Trigger redo operation")
    prev_saved_trigger = param.Integer(default=0, doc="Load previous saved view")
    next_saved_trigger = param.Integer(default=0, doc="Load next saved view")
    keyboard_trigger = param.String(default='', doc="Keyboard shortcut trigger")
    image_nav_trigger = param.String(default='', doc="Image navigation keyboard trigger")
    
    # Keyboard shortcuts configuration (JSON string)
    shortcuts_config = param.String(default='', doc="JSON string of keyboard shortcuts configuration")

    
    _template = """
    <style>
        .leaflet-container {
            background-color: #dadae3 !important;
            user-select: none !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
        }
        .leaflet-tile-pane, .leaflet-tile-container {
            background-color: transparent !important;
        }
        /* Drawing toolbar styles */
        .leaflet-draw-toolbar a {
            background-color: white !important;
            user-select: none !important;
            -webkit-user-select: none !important;
        }
        /* Disable text selection on all leaflet elements */
        .leaflet-control, .leaflet-bar, .leaflet-control a {
            user-select: none !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
        }
        /* Custom pen cursor */
        .pen-cursor {
            cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 16 16'%3E%3Cpath fill='%23000' d='M12.854 0.854l2.292 2.292-9.5 9.5-2.292 0.146-0.146-2.292 9.5-9.5zM13.207 3.5l-1.207-1.207-7.5 7.5 0.073 1.134 1.134 0.073 7.5-7.5z'/%3E%3C/svg%3E") 0 16, crosshair !important;
        }
    </style>
    <div id="map_div" style="position: relative; width: 100%; height: 100%; min-height: 600px;"></div>
    """
    
    _scripts = {
        'render': """
            console.log('=== SVS VIEWER v5.0 - Fixed Viewport ===');
            console.log('Render script executed');
            
            // Inline MiniMap CSS
            if (!document.getElementById('minimap-css')) {
                const style = document.createElement('style');
                style.id = 'minimap-css';
                style.textContent = `.leaflet-control-minimap{border:rgba(255,255,255,1) solid;box-shadow:0 1px 5px rgba(0,0,0,.65);border-radius:3px;background:#f8f8f9;transition:all .6s}.leaflet-control-minimap a{background-color:rgba(255,255,255,1);background-repeat:no-repeat;z-index:99999;transition:all .6s}.leaflet-control-minimap a.minimized-bottomright{-webkit-transform:rotate(180deg);transform:rotate(180deg);border-radius:0}.leaflet-control-minimap a.minimized-topleft{-webkit-transform:rotate(0deg);transform:rotate(0deg);border-radius:0}.leaflet-control-minimap a.minimized-bottomleft{-webkit-transform:rotate(270deg);transform:rotate(270deg);border-radius:0}.leaflet-control-minimap a.minimized-topright{-webkit-transform:rotate(90deg);transform:rotate(90deg);border-radius:0}.leaflet-control-minimap-toggle-display{background-image:url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOSIgaGVpZ2h0PSIxOSI+PHBhdGggZD0iTTkuNSAwTDAgOS41IDE5IDkuNXoiIGZpbGw9IiNmZmYiLz48L3N2Zz4=);background-size:cover;position:absolute;border-radius:3px 0 0}.leaflet-control-minimap-toggle-display-bottomright{bottom:0;right:0}.leaflet-control-minimap-toggle-display-topleft{top:0;left:0;-webkit-transform:rotate(180deg);transform:rotate(180deg)}.leaflet-control-minimap-toggle-display-bottomleft{bottom:0;left:0;-webkit-transform:rotate(90deg);transform:rotate(90deg)}.leaflet-control-minimap-toggle-display-topright{top:0;right:0;-webkit-transform:rotate(270deg);transform:rotate(270deg)}`;
                document.head.appendChild(style);
                console.log('✓ MiniMap CSS injected');
            }
        """,
        
        'after_layout': """
            console.log('=== after_layout v11.0: Dynamic Keyboard Shortcuts + MiniMap + Freehand Drawing ===');
            
            // Parse shortcuts configuration from Python
            let shortcuts = {};
            try {
                if (data.shortcuts_config) {
                    shortcuts = JSON.parse(data.shortcuts_config);
                    console.log('✓ Loaded custom keyboard shortcuts:', Object.keys(shortcuts).length, 'actions');
                }
            } catch (e) {
                console.error('Error parsing shortcuts config:', e);
            }
            
            // Helper function to check if key combination matches
            function matchesKeyCombination(event, keyCombo) {
                const parts = keyCombo.split('+');
                let hasCtrl = false, hasCmd = false, hasAlt = false, hasShift = false;
                let mainKey = null;
                
                for (const part of parts) {
                    const partLower = part.toLowerCase();
                    if (partLower === 'ctrl') hasCtrl = true;
                    else if (partLower === 'cmd' || partLower === 'meta') hasCmd = true;
                    else if (partLower === 'alt') hasAlt = true;
                    else if (partLower === 'shift') hasShift = true;
                    else mainKey = part;
                }
                
                // Check modifiers
                const ctrlMatch = hasCtrl || hasCmd ? (event.ctrlKey || event.metaKey) : (!event.ctrlKey && !event.metaKey);
                const altMatch = hasAlt ? event.altKey : !event.altKey;
                const shiftMatch = hasShift ? event.shiftKey : !event.shiftKey;
                
                // Check main key
                let keyMatch = false;
                if (mainKey) {
                    keyMatch = event.key.toLowerCase() === mainKey.toLowerCase();
                }
                
                return ctrlMatch && altMatch && shiftMatch && keyMatch;
            }
            
            // Keyboard shortcuts handler - set up once
            if (!window.keyboardShortcutsRegistered) {
                document.addEventListener('keydown', function(e) {
                    // Check each configured shortcut
                    for (const [actionName, config] of Object.entries(shortcuts)) {
                        const keys = config.keys || [];
                        
                        // Check if any of the key combinations match
                        for (const keyCombo of keys) {
                            if (matchesKeyCombination(e, keyCombo)) {
                                e.preventDefault();
                                const action = config.action || actionName;
                                console.log('⌨️  Keyboard:', action, '(' + keyCombo + ')');
                                data.keyboard_trigger = action;
                                return; // Exit after first match
                            }
                        }
                    }
                });
                window.keyboardShortcutsRegistered = true;
                console.log('✓ Keyboard shortcuts registered dynamically from configuration');
            }
            
            // Inline freehand drawing module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'freehand_drawing.js'), 'r').read() + """
            
            // Inline scale bar module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'scale_bar.js'), 'r').read() + """
            
            // Inline minimap overview module
            """ + open(os.path.join(os.path.dirname(__file__), '..', 'Features', 'minimap_overview.js'), 'r').read() + """
            
            // Define DZITileLayer if not already defined (fallback for CDN issues)
            if (typeof DZITileLayer === 'undefined' && typeof L !== 'undefined') {
                console.log('Defining DZITileLayer inline...');
                var DZITileLayer = L.TileLayer.extend({
                    getTileUrl: function(coords) {
                        return 'http://localhost:' + data.dzi_server_port + '/' + 
                               data.dzi_url.replace('.dzi', '_files') + '/' + 
                               coords.z + '/' + coords.x + '_' + coords.y + '.png';
                    }
                });
                console.log('✓ DZITileLayer defined');
            }
            
            // Wait for essential libraries to load before initializing
            let initAttempts = 0;
            const maxAttempts = 50; // 5 seconds max wait
            
            function checkLibraries() {
                const leafletReady = typeof L !== 'undefined';
                const dziReady = typeof DZITileLayer !== 'undefined';
                const minimapReady = leafletReady && typeof L.Control.MiniMap !== 'undefined';
                
                // Only require essential libraries (Leaflet, DZI)
                // MiniMap is optional
                return {
                    ready: leafletReady && dziReady,
                    leaflet: leafletReady,
                    dzi: dziReady,
                    minimap: minimapReady
                };
            }
            
            function initializeMap() {
                initAttempts++;
                const libStatus = checkLibraries();
                
                console.log('📦 Library Check (attempt ' + initAttempts + '):');
                console.log('  - Leaflet:', libStatus.leaflet ? '✓' : '❌');
                console.log('  - Leaflet DeepZoom:', libStatus.dzi ? '✓' : '❌');
                console.log('  - Leaflet MiniMap:', libStatus.minimap ? '✓ (optional)' : '❌ (optional)');
                
                if (!libStatus.ready) {
                    if (initAttempts >= maxAttempts) {
                        console.error('❌ Timeout waiting for libraries to load');
                        return;
                    }
                    console.log('⏳ Waiting for libraries to load...');
                    setTimeout(initializeMap, 100);
                    return;
                }
                
                console.log('✓ Essential libraries loaded, initializing map...');
                if (!libStatus.minimap) {
                    console.warn('⚠️ MiniMap plugin not available - continuing without it');
                }
                
                // Panel ReactiveHTML components are in shadow DOM
                // Need to find the shadow root first
                let mapDiv = null;
                
                // Search ALL elements in the document for shadow roots
                const allElements = document.querySelectorAll('*');
                console.log('Total elements in document:', allElements.length);
                
                let shadowRootsFound = 0;
                for (let element of allElements) {
                    if (element.shadowRoot) {
                        shadowRootsFound++;
                        
                        // Check specifically for ReactiveHTML component
                        if (element.className.includes('ReactiveHTML')) {
                            console.log('✓ Found ReactiveHTML shadow root!');
                            
                            // Try to find the map div by ID using querySelector (searches all descendants)
                            mapDiv = element.shadowRoot.querySelector('#map_div');
                            
                            if (mapDiv) {
                                console.log('✓ Found map_div by querySelector!');
                                break;
                            }
                            
                            // Fallback: Search ALL divs in shadow root (including nested ones)
                            const allDivs = element.shadowRoot.querySelectorAll('div');
                            console.log('  DIV children found:', allDivs.length);
                            
                            for (let div of allDivs) {
                                const style = div.getAttribute('style') || '';
                                const id = div.getAttribute('id') || '';
                                console.log('  Checking div - id:', id, 'style:', style);
                                
                                // Our map_div has id="map_div"
                                if (id === 'map_div') {
                                    mapDiv = div;
                                    console.log('✓ Found map_div by id attribute!');
                                    break;
                                }
                                
                                // Or look for the position: relative style with min-height
                                if (style.includes('position: relative') && style.includes('min-height')) {
                                    mapDiv = div;
                                    console.log('✓ Found map_div by style attributes!');
                                    break;
                                }
                            }
                            
                            if (mapDiv) break;
                        }
                    }
                }
                
                console.log('Total shadow roots searched:', shadowRootsFound);
                
                if (!mapDiv) {
                    console.error('Map div not found! Aborting.');
                    return;
                }
                
                console.log('✓ Map div found, initializing Leaflet map...');
                
                // CRITICAL: Remove existing map if it exists to prevent stale tile URLs
                if (state.map) {
                    console.log('Removing existing map instance...');
                    state.map.remove();
                    state.map = null;
                    state.tileLayer = null;
                }
                    
                const imageWidth = data.width_px;
                const imageHeight = data.height_px;
                const maxZoom = data.max_zoom;
                
                console.log('Image size:', imageWidth, 'x', imageHeight);
                console.log('Max DZI zoom level:', maxZoom);
                
                // Calculate the scale factor - at max zoom, 1 pixel = 1 coordinate unit
                // DZI max zoom (17) shows full resolution image
                const scale = Math.pow(2, maxZoom);
                const scaledWidth = imageWidth / scale;
                const scaledHeight = imageHeight / scale;
                
                console.log('Scale at zoom 0:', scaledWidth, 'x', scaledHeight);
                
                // SOLUTION AFTER INVESTIGATION:
                // Problem: DZI level 8 tile is 182×139px, but level 9+ tiles are 257×257px
                // This inconsistency causes Leaflet to scale incorrectly
                //
                // FIX: Start at DZI level 9 (not 8) where tiles are consistently sized
                // At Leaflet zoom 0 = DZI level 9 (2×2 tiles = 512×512 coordinate space)
                // This gives uniform tile sizes across all zoom levels
                
                console.log('Container size:', mapDiv.offsetWidth, 'x', mapDiv.offsetHeight);
                console.log('Image dimensions:', imageWidth, 'x', imageHeight);
                
                // Get start level and center offset from metadata
                //const startLevel = data.recommended_start_level || 9;
                const startLevel = 8;
                console.log('Using fixed start level:', startLevel);
                const centerOffsetY = data.center_offset_y || -1.15;
                
                console.log('Starting at DZI level', startLevel);
                console.log('Center offset Y multiplier:', centerOffsetY);
                
                // Calculate dimensions at start level
                const scaleAtStart = Math.pow(2, maxZoom - startLevel);
                const widthAtStartLevel = imageWidth / scaleAtStart;
                const heightAtStartLevel = imageHeight / scaleAtStart;
                
                console.log('Image at level', startLevel + ':', widthAtStartLevel.toFixed(1), 'x', heightAtStartLevel.toFixed(1), 'pixels');
                
                // Use actual image dimensions as coordinate space
                const centerY = heightAtStartLevel / 2;
                const centerX = widthAtStartLevel / 2;
                
                state.map = L.map(mapDiv, {
                    crs: L.CRS.Simple,
                    minZoom: 0,
                    maxZoom: maxZoom - startLevel,  // Max Leaflet zoom
                    zoomControl: false,  // Disable default zoom control, we'll add custom one
                    attributionControl: false,
                    zoomSnap: 1,
                    zoomDelta: 1,
                    wheelPxPerZoomLevel: 60,
                    boxZoom: false  // Disable box zoom (Shift+drag) to allow freehand drawing
                });
                
                console.log('Map object created, max Leaflet zoom:', maxZoom - startLevel);
                
                // Add custom zoom control with magnification display
                L.Control.CustomZoom = L.Control.extend({
                    options: {
                        position: 'topleft'
                    },
                    
                    onAdd: function(map) {
                        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                        container.style.display = 'flex';
                        container.style.flexDirection = 'column';
                        container.style.gap = '0';
                        
                        // Zoom in button
                        const zoomInButton = L.DomUtil.create('a', 'leaflet-control-zoom-in', container);
                        zoomInButton.innerHTML = '+';
                        zoomInButton.href = '#';
                        zoomInButton.title = 'Zoom in';
                        zoomInButton.setAttribute('role', 'button');
                        zoomInButton.setAttribute('aria-label', 'Zoom in');
                        
                        // Magnification display
                        const magDisplay = L.DomUtil.create('div', 'leaflet-control-zoom-mag', container);
                        magDisplay.style.backgroundColor = 'white';
                        magDisplay.style.padding = '2px 8px';
                        magDisplay.style.textAlign = 'center';
                        magDisplay.style.fontSize = '12px';
                        magDisplay.style.fontWeight = 'bold';
                        magDisplay.style.borderTop = '1px solid #ccc';
                        magDisplay.style.borderBottom = '1px solid #ccc';
                        magDisplay.style.cursor = 'default';
                        magDisplay.innerHTML = '0x';
                        
                        // Zoom out button
                        const zoomOutButton = L.DomUtil.create('a', 'leaflet-control-zoom-out', container);
                        zoomOutButton.innerHTML = '−';
                        zoomOutButton.href = '#';
                        zoomOutButton.title = 'Zoom out';
                        zoomOutButton.setAttribute('role', 'button');
                        zoomOutButton.setAttribute('aria-label', 'Zoom out');
                        
                        // Event handlers
                        L.DomEvent.on(zoomInButton, 'click', function(e) {
                            L.DomEvent.stopPropagation(e);
                            L.DomEvent.preventDefault(e);
                            map.zoomIn();
                        });
                        
                        L.DomEvent.on(zoomOutButton, 'click', function(e) {
                            L.DomEvent.stopPropagation(e);
                            L.DomEvent.preventDefault(e);
                            map.zoomOut();
                        });
                        
                        L.DomEvent.disableClickPropagation(container);
                        L.DomEvent.disableScrollPropagation(container);
                        
                        // Update magnification display
                        this._magDisplay = magDisplay;
                        this._updateMagDisplay = function() {
                            const zoom = map.getZoom();
                            
                            // Calculate actual magnification based on SVS metadata
                            // DZI level = startLevel + Leaflet zoom
                            const dziLevel = startLevel + Math.floor(zoom);
                            
                            // Base magnification from SVS metadata (e.g., 40×)
                            const baseMag = data.objective_power || 40.0;
                            
                            // Downsample at this DZI level: 2^(maxZoom - dziLevel)
                            const downsample = Math.pow(2, maxZoom - dziLevel);
                            
                            // Actual magnification = base / downsample
                            const actualMag = baseMag / downsample;
                            
                            // Format based on magnitude
                            let magText;
                            if (actualMag >= 1.0) {
                                // Show whole numbers for 1× and above
                                magText = actualMag.toFixed(0) + '×';
                            } else if (actualMag >= 0.01) {
                                // Show 2-3 decimals for smaller magnifications
                                magText = actualMag.toFixed(3) + '×';
                            } else {
                                // Scientific notation for very small magnifications
                                magText = actualMag.toExponential(1);
                            }
                            
                            magDisplay.innerHTML = magText;
                        };
                        
                        map.on('zoomend', this._updateMagDisplay, this);
                        this._updateMagDisplay();
                        
                        return container;
                    },
                    
                    onRemove: function(map) {
                        map.off('zoomend', this._updateMagDisplay, this);
                    }
                });
                
                // Add the custom zoom control
                new L.Control.CustomZoom().addTo(state.map);
                console.log('✓ Custom zoom control with magnification display added');
                
                // Set initial view at zoom 0 with center adjusted from metadata
                // Lower Y value = higher on screen in Leaflet
                const adjustedCenterY = centerY * centerOffsetY;
                state.map.setView([adjustedCenterY, centerX], 0);
                console.log('Initial view set with adjusted center:', [adjustedCenterY, centerX], '(offset multiplier:', centerOffsetY + ')');
                
                // Add DZI tile layer with proper coordinate system
                const dziBaseName = data.dzi_url.replace('.dzi', '');
                const baseUrl = 'http://' + window.location.hostname + ':' + data.dzi_server_port + '/' + dziBaseName + '_files';
                
                console.log('DZI base URL:', baseUrl);
                console.log('DZI zoom levels: 0 (small) to', maxZoom, '(full res)');
                
                // Create custom tile layer with DZI-specific getTileUrl and proper edge tile handling
                const DZITileLayer = L.TileLayer.extend({
                    getTileUrl: function(coords) {
                        // Map Leaflet zoom to DZI zoom: DZI zoom = Leaflet zoom + startLevel
                        const dziZoom = coords.z + startLevel;
                        
                        // Calculate how many tiles exist at this DZI zoom level
                        // Tiles double at each level starting from level 9
                        const tilesAtThisZoom = Math.pow(2, Math.max(0, dziZoom - 8));
                        
                        // ONLY accept coordinates in the valid range [0, tilesAtThisZoom)
                        if (coords.x < 0 || coords.x >= tilesAtThisZoom || 
                            coords.y < 0 || coords.y >= tilesAtThisZoom) {
                            return '';  // Don't load tiles outside valid range
                        }
                        
                        // Valid coordinates - request the tile from DZI
                        const url = baseUrl + '/' + dziZoom + '/' + coords.x + '_' + coords.y + '.png';
                        
                        // DETAILED LOGGING for debugging aspect ratio issues
                        if (coords.z <= 2) {  // Only log first few zoom levels to avoid spam
                            console.log(`[TILE] Leaflet zoom=${coords.z}, DZI level=${dziZoom}, ` +
                                       `coords=(${coords.x},${coords.y}), tiles=${tilesAtThisZoom}x${tilesAtThisZoom}, ` +
                                       `url=${dziZoom}/${coords.x}_${coords.y}.png`);
                        }
                        
                        return url;
                    },
                    
                    // CRITICAL FIX: Override createTile to handle variable tile sizes
                    // DZI tiles can be ANY size at ANY zoom level - we must use actual loaded dimensions
                    createTile: function(coords, done) {
                        const tile = document.createElement('img');
                        
                        // Get the tile URL
                        const url = this.getTileUrl(coords);
                        
                        if (!url) {
                            // Empty tile
                            done(null, tile);
                            return tile;
                        }
                        
                        // Calculate image dimensions at this DZI level for reference
                        const dziZoom = coords.z + startLevel;
                        const scaleAtLevel = Math.pow(2, maxZoom - dziZoom);
                        const levelWidth = imageWidth / scaleAtLevel;
                        const levelHeight = imageHeight / scaleAtLevel;
                        
                        // DZI tile configuration
                        const baseTileSize = 256;  // Base tile size without overlap
                        const overlap = 1;  // Standard DZI overlap
                        const fullTileSize = baseTileSize + overlap;  // Expected: 257
                        
                        // Calculate tile grid dimensions
                        const tileCols = Math.ceil(levelWidth / baseTileSize);
                        const tileRows = Math.ceil(levelHeight / baseTileSize);
                        
                        // Calculate expected dimensions (for reference/debugging only)
                        let expectedWidth, expectedHeight;
                        
                        if (coords.x < tileCols - 1) {
                            expectedWidth = fullTileSize;
                        } else {
                            const remainingWidth = levelWidth - (coords.x * baseTileSize);
                            expectedWidth = Math.ceil(Math.min(remainingWidth + overlap, fullTileSize));
                        }
                        
                        if (coords.y < tileRows - 1) {
                            expectedHeight = fullTileSize;
                        } else {
                            const remainingHeight = levelHeight - (coords.y * baseTileSize);
                            expectedHeight = Math.ceil(Math.min(remainingHeight + overlap, fullTileSize));
                        }
                        
                        // Set tile properties
                        tile.alt = '';
                        tile.setAttribute('role', 'presentation');
                        
                        // **KEY FIX**: Hide tile until we know its actual dimensions
                        tile.style.visibility = 'hidden';
                        
                        // Load the image and use its ACTUAL dimensions
                        L.DomEvent.on(tile, 'load', function() {
                            // Get actual loaded image dimensions - THIS is the truth
                            const actualWidth = tile.naturalWidth;
                            const actualHeight = tile.naturalHeight;
                            
                            // Set exact dimensions based on what was actually loaded
                            tile.width = actualWidth;
                            tile.height = actualHeight;
                            tile.style.width = actualWidth + 'px';
                            tile.style.height = actualHeight + 'px';
                            tile.style.maxWidth = actualWidth + 'px';
                            tile.style.maxHeight = actualHeight + 'px';
                            tile.style.minWidth = actualWidth + 'px';
                            tile.style.minHeight = actualHeight + 'px';
                            
                            // Now show the properly sized tile
                            tile.style.visibility = 'visible';
                            
                            // Debug logging at low zoom levels
                            if (coords.z <= 2) {
                                const mismatch = (actualWidth !== expectedWidth || actualHeight !== expectedHeight);
                                if (mismatch) {
                                    console.log(`[TILE SIZE] DZI level ${dziZoom}, tile (${coords.x},${coords.y}): ` +
                                               `Expected ${expectedWidth}×${expectedHeight}px, ` +
                                               `Got ${actualWidth}×${actualHeight}px ` +
                                               `(grid: ${tileCols}×${tileRows}, level: ${Math.round(levelWidth)}×${Math.round(levelHeight)})`);
                                }
                            }
                            
                            this._tileOnLoad(done, tile);
                        }.bind(this));
                        
                        L.DomEvent.on(tile, 'error', function(e) {
                            console.error(`[TILE ERROR] DZI level ${dziZoom}, tile (${coords.x},${coords.y}): ${url}`);
                            this._tileOnError(done, tile, e);
                        }.bind(this));
                        
                        if (this.options.crossOrigin || this.options.crossOrigin === '') {
                            tile.crossOrigin = this.options.crossOrigin === true ? '' : this.options.crossOrigin;
                        }
                        
                        tile.src = url;
                        
                        return tile;
                    }
                });
                
                // Create tile layer with proper edge tile handling
                state.tileLayer = new DZITileLayer('', {
                    tileSize: 257,  // Standard tile size (DZI tiles with 1px overlap)
                    noWrap: true,
                    minNativeZoom: 0,
                    maxNativeZoom: maxZoom - startLevel,
                    tms: false,
                    updateWhenIdle: false,  // Update tiles while panning
                    updateWhenZooming: true,  // Update tiles while zooming
                    keepBuffer: 2  // Keep 2 tile rows/cols around viewport
                }).addTo(state.map);
                
                console.log('DZI tile layer added with edge tile handling');
                console.log('Map center:', state.map.getCenter());
                console.log('Map zoom:', state.map.getZoom());
                console.log('Map pixel bounds:', state.map.getPixelBounds());
                console.log('Map size:', state.map.getSize());
                
                // Log on every zoom to see coordinate space changes
                state.map.on('zoomend', function() {
                    const zoom = state.map.getZoom();
                    const center = state.map.getCenter();
                    const bounds = state.map.getBounds();
                    const pixelBounds = state.map.getPixelBounds();
                    console.log(`[ZOOM] Level=${zoom}, Center=[${center.lat.toFixed(1)}, ${center.lng.toFixed(1)}], ` +
                               `Bounds=${JSON.stringify([[bounds.getSouth().toFixed(1), bounds.getWest().toFixed(1)], ` +
                               `[bounds.getNorth().toFixed(1), bounds.getEast().toFixed(1)]])}, ` +
                               `PixelBounds=${JSON.stringify(pixelBounds)}`);
                });
            
            // Update zoom indicator
            function updateZoomInfo() {
                if (!state.map) return;
                try {
                    const currentZoom = state.map.getZoom();
                    if (typeof currentZoom === 'undefined' || isNaN(currentZoom)) return;
                    
                    // Calculate DZI level from Leaflet zoom
                    const dziLevel = startLevel + Math.floor(currentZoom);
                    const magnification = Math.pow(2, currentZoom);
                    const zoomText = `Level ${dziLevel} (${magnification.toFixed(2)}x)`;
                    
                    // Update Panel parameters
                    if (data) {
                        if (typeof data.zoom_level !== 'undefined') {
                            data.zoom_level = zoomText;
                        }
                        if (typeof data.zoom !== 'undefined') {
                            data.zoom = Math.floor(currentZoom);
                        }
                    }
                    
                    console.log('Zoom updated - Leaflet zoom:', currentZoom, 'DZI level:', dziLevel, 'Magnification:', magnification.toFixed(2) + 'x');
                } catch (e) {
                    console.error('Error in updateZoomInfo:', e);
                }
            }
            
            // Event listeners
            state.map.on('zoom', updateZoomInfo);
            state.map.on('zoomend', updateZoomInfo);  // Also update on zoomend
            state.map.on('move', () => {
                if (!state.map) return;
                const center = state.map.getCenter();
                data.center = [center.lat, center.lng];
            });
            
            // Initialize zoom display
            updateZoomInfo();
            
            // Initialize minimap from external module
            if (typeof initializeMiniMap === 'function') {
                initializeMiniMap(state.map, DZITileLayer, imageWidth, imageHeight, startLevel, maxZoom, state);
            } else {
                console.error('initializeMiniMap function not found. Make sure minimap_overview.js is loaded.');
            }
            
            // Initialize scale bar from external module
            // mm/pixel ratio at base resolution (DZI max zoom level)
            const mmPerPixel = data.mm_per_pixel || 0.0004;
            
            console.log('Using mm_per_pixel from metadata:', mmPerPixel);

            if (typeof initializeScaleBar === 'function') {
                initializeScaleBar(state.map, mmPerPixel, startLevel, maxZoom);
            } else {
                console.error('initializeScaleBar function not found. Make sure scale_bar.js is loaded.');
            }
            
            // ADD DRAWING CAPABILITIES
            // Create feature group to store drawn items
            state.drawnItems = new L.FeatureGroup();
            state.map.addLayer(state.drawnItems);
            
            // Initialize freehand drawing from external module
            if (typeof initializeFreehandDrawing === 'function') {
                initializeFreehandDrawing(state.map, state.drawnItems);
                console.log('Map initialized successfully with freehand drawing tool');
            } else {
                console.error('initializeFreehandDrawing function not found. Make sure freehand_drawing.js is loaded.');
            }
            
            // ANNOTATION SAVE/LOAD FUNCTIONS
            window.getAnnotationsData = function() {
                if (!state.drawnItems) return null;
                
                const annotations = [];
                state.drawnItems.eachLayer(function(layer) {
                    if (layer instanceof L.Polyline) {
                        const geojson = layer.toGeoJSON();
                        annotations.push({
                            type: 'polyline',
                            coordinates: geojson.geometry.coordinates,
                            color: layer.options.originalColor || layer.options.color,
                            weight: layer.options.originalWeight || layer.options.weight
                        });
                    }
                });
                
                const currentZoom = state.map.getZoom();
                const currentCenter = state.map.getCenter();
                
                return {
                    image_name: data.image_name,
                    zoom: currentZoom,
                    center: [currentCenter.lat, currentCenter.lng],
                    annotations: annotations,
                    timestamp: new Date().toISOString()
                };
            };
            
            window.loadAnnotationsData = function(data) {
                if (!state.drawnItems || !state.map) return;
                
                console.log('Loading annotations:', data);
                
                // Clear existing annotations
                state.drawnItems.clearLayers();
                
                // Load annotations
                if (data.annotations && data.annotations.length > 0) {
                    data.annotations.forEach(function(anno) {
                        if (anno.type === 'polyline') {
                            // Convert GeoJSON coordinates to LatLng
                            const latlngs = anno.coordinates.map(function(coord) {
                                return [coord[1], coord[0]]; // GeoJSON is [lng, lat], Leaflet is [lat, lng]
                            });
                            
                            const polyline = L.polyline(latlngs, {
                                color: anno.color,
                                weight: anno.weight,
                                originalColor: anno.color,
                                originalWeight: anno.weight
                            });
                            
                            state.drawnItems.addLayer(polyline);
                        }
                    });
                    console.log('Loaded', data.annotations.length, 'annotations');
                }
                
                // Restore view if available
                if (data.zoom !== undefined && data.center) {
                    state.map.setView(data.center, data.zoom);
                    console.log('Restored view: zoom', data.zoom, 'center', data.center);
                }
            };
            
            } // End of initializeMap function
            
            // Start the initialization process
            initializeMap();
        """,
        
        'dzi_url': """
            // When dzi_url changes, force re-initialization
            console.log('=== DZI URL CHANGED ===');
            console.log('New dzi_url:', data.dzi_url);
            
            // Only re-initialize if we have a valid map already
            // This prevents re-initialization on sidebar toggle
            if (state.map) {
                console.log('Map exists, triggering re-initialization...');
                // Trigger after_layout to re-initialize the map
                self.after_layout();
            } else {
                console.log('No map yet, skipping re-initialization (will initialize on first render)');
            }
        """,
        
        'save_annotation_trigger': """
            // Triggered when save is requested from Python
            console.log('Save annotation trigger:', data.save_annotation_trigger);
            if (typeof window.getAnnotationsData === 'function') {
                const annotationsData = window.getAnnotationsData();
                if (annotationsData) {
                    // Send data back to Python
                    data.annotation_data = JSON.stringify(annotationsData);
                    console.log('Annotations data sent to Python');
                } else {
                    console.log('No annotations to save');
                    data.annotation_data = JSON.stringify({
                        zoom: state.map ? state.map.getZoom() : 0,
                        center: state.map ? [state.map.getCenter().lat, state.map.getCenter().lng] : [0, 0],
                        annotations: [],
                        timestamp: new Date().toISOString()
                    });
                }
            }
        """,
        
        'load_annotation_trigger': """
            // Triggered when load is requested from Python
            console.log('Load annotation trigger:', data.load_annotation_trigger);
            if (data.annotation_data && typeof window.loadAnnotationsData === 'function') {
                try {
                    const annotationsData = JSON.parse(data.annotation_data);
                    
                    // Check if this is a special action (like toggle_minimap)
                    if (annotationsData.action === 'toggle_minimap') {
                        console.log('🗺️  Toggle minimap action received');
                        if (typeof state !== 'undefined' && state.miniMap && state.miniMap._toggleButton) {
                            state.miniMap._toggleButton.click();
                            console.log('✓ Minimap toggled via keyboard shortcut');
                        } else {
                            console.warn('⚠️ Minimap not available or not initialized');
                        }
                    } else {
                        // Normal annotation loading
                        window.loadAnnotationsData(annotationsData);
                        console.log('Annotations loaded successfully');
                    }
                } catch (e) {
                    console.error('Error loading annotations:', e);
                }
            }
        """
    }
    
    __css__ = [
        'https://unpkg.com/leaflet@1.7.1/dist/leaflet.css'
    ]
    __javascript__ = [
        'https://unpkg.com/leaflet@1.7.1/dist/leaflet.js'
    ]


class SVSAnnotationTool:
    """
    Main SVS viewer tool with annotation saving/loading capabilities.
    """
    
    def __init__(self, svs_path, dzi_path=None, shortcut_manager=None):
        self.svs_path = svs_path
        self.dzi_path = dzi_path
        self.shortcut_manager = shortcut_manager
        
        print(f"Initializing DZI Viewer")
        print(f"Base path: {svs_path}")
        print(f"DZI path: {dzi_path}")
        
        # Load metadata for this specific image
        base_name = os.path.basename(svs_path).replace('.svs', '')
        self.image_name = base_name
        
        # Get metadata path from dzi_path or search for it
        if dzi_path:
            metadata_path = dzi_path.replace('.dzi', '_metadata.json')
        else:
            # Find metadata file - check all possible locations
            metadata_path = None
            for collection in ['BRACS', 'TCGA', 'BACH']:
                potential_path = f"/data/dzi_datasets/{collection}/{base_name}_metadata.json"
                if os.path.exists(potential_path):
                    metadata_path = potential_path
                    break
            
            # Fallback to old location
            if not metadata_path:
                metadata_path = f"/data/dzi_output/{base_name}_metadata.json"
        
        metadata = load_metadata(metadata_path)

        # Load scalebar metadata (mpp_x → mm_per_pixel)
        self.mm_per_pixel = load_scalebar_metadata(base_name)
        
        # Load SVS metadata for accurate magnification display
        svs_metadata_path = f"/data/svs_metadata/{base_name}_svs_scalebar_metadata.json"
        self.objective_power = 40.0  # Default
        self.level_downsamples = [1.0, 4.0, 16.0, 32.0]  # Default
        
        if os.path.exists(svs_metadata_path):
            try:
                with open(svs_metadata_path, 'r') as f:
                    svs_metadata = json.load(f)
                    self.objective_power = float(svs_metadata.get('objective_power', 40.0))
                    self.level_downsamples = svs_metadata.get('level_downsamples', [1.0, 4.0, 16.0, 32.0])
                    logger.info(f"✓ Loaded SVS metadata: {self.objective_power}× objective, {len(self.level_downsamples)} levels")
            except Exception as e:
                logger.warning(f"⚠ Error loading SVS metadata: {e}")
        
        # Initialize annotation directories
        self.live_dir, self.saved_dir = ensure_annotation_directories(self.image_name)
        
        # Live tracking state
        self.live_tracking_index = get_next_live_tracking_number(self.live_dir)
        self.current_live_index = self.live_tracking_index - 1 if self.live_tracking_index > 0 else -1
        
        # Track last saved state for change detection
        self.last_saved_state = None
        self.initial_state_saved = False
        
        # Saved views state
        self.saved_views = get_saved_views_list(self.saved_dir)
        self.current_saved_index = -1  # -1 means no saved view loaded
        self._manual_save_pending = False
        
        # Navigation state tracking - prevents duplicate saves during undo/redo
        self._is_loading_state = False  # Flag to prevent auto-save during navigation
        self._navigation_timestamp = 0  # Track when navigation occurred
        
        # Ink status tracking (simple attributes, not Panel parameters)
        status_data = load_ink_status(self.image_name)
        self.done_status = status_data.get('done', False)
        self.ink_found_status = status_data.get('ink_found', False)
        self.parent_app = None  # Will be set by InteractiveSVSApp
        
        # Get dimensions from metadata (no need to open SVS file)
        orig_dims = metadata.get('original_dimensions', {})
        self.dimensions = (orig_dims.get('width', 100000), orig_dims.get('height', 100000))
        
        # DZI levels from metadata
        dzi_levels = metadata.get('dzi_levels', 18)
        self.level_count = dzi_levels
        
        # Calculate level dimensions for DZI pyramid
        # DZI levels go from 0 (smallest) to dzi_levels-1 (full resolution)
        self.level_dimensions = []
        for level in range(dzi_levels):
            scale = 2 ** (dzi_levels - 1 - level)
            w = max(1, self.dimensions[0] // scale)
            h = max(1, self.dimensions[1] // scale)
            self.level_dimensions.append((w, h))
        
        logger.info(f"Image dimensions: {self.dimensions}")
        logger.info(f"DZI levels: {self.level_count}")
        
        # Convert level dimensions to list format for JavaScript
        level_dims_list = [[int(w), int(h)] for w, h in self.level_dimensions]
        
        # Get DZI relative path for tile server
        if self.dzi_path:
            # Convert absolute container path to relative path from /data/dzi_datasets/
            dzi_relative = self.dzi_path.replace('/data/dzi_datasets/', '')
        else:
            # Fallback to just filename
            dzi_relative = os.path.basename(svs_path).replace('.svs', '.dzi')
        
        print(f"DZI relative path for viewer: {dzi_relative}")
        
        # Get metadata values or use defaults
        #start_level = metadata.get('recommended_start_level', 9)
        start_level = 8
        center_offset = metadata.get('center_offset_y', -1.15)

        # Get shortcuts configuration as JSON string
        shortcuts_json = ''
        if self.shortcut_manager:
            shortcuts_json = json.dumps(self.shortcut_manager.shortcuts)
            logger.info("Passing keyboard shortcuts config to viewer")
        
        # Create viewer with DZI configuration using metadata
        self.viewer = SVSLeafletViewer(
            dzi_url=dzi_relative,
            max_zoom=dzi_levels - 1,  # DZI has dzi_levels (0 to dzi_levels-1)
            width_px=self.dimensions[0],
            height_px=self.dimensions[1],
            level_dimensions=level_dims_list,
            start_level=start_level,
            center_offset_y=center_offset,
            dzi_server_port=DZI_SERVER_PORT,
            image_name=self.image_name,
            mm_per_pixel=self.mm_per_pixel,  # Pass to viewer
            objective_power=self.objective_power,  # Pass SVS metadata for magnification display
            level_downsamples=self.level_downsamples,  # Pass SVS downsample factors
            shortcuts_config=shortcuts_json,  # Pass keyboard shortcuts configuration
            min_height=600,
            sizing_mode='stretch_both'
        )
        
        # Watch for annotation data changes from JavaScript
        self.viewer.param.watch(self._on_annotation_data_change, 'annotation_data')
        
        # Set up periodic check (every 1 second) - only saves if changed AND not navigating
        self.auto_save_callback = pn.state.add_periodic_callback(
            self._check_and_save_if_changed,
            period=1000  # 1000 ms = 1 second
        )
        
        logger.info(f"✓ Live tracking enabled (1-second interval, saves only when view changes)")
    
    def _check_and_save_if_changed(self):
        """Check if view has changed and save only if different from last save"""
        try:
            # CRITICAL: Skip if we're currently loading a state (undo/redo/prev/next)
            if self._is_loading_state:
                return
            
            # CRITICAL: Skip if navigation happened less than 2 seconds ago
            # This gives JavaScript time to load and render the state
            time_since_navigation = time.time() - self._navigation_timestamp
            if time_since_navigation < 2.0:  # 2 second grace period
                return
            
            # Trigger JavaScript to get current state
            self.viewer.save_annotation_trigger += 1
        except Exception as e:
            logger.error(f"Error in change detection: {e}")
    
    def _compare_states(self, state1, state2):
        """Compare two annotation states to detect changes"""
        if state1 is None or state2 is None:
            return True  # Consider changed if either is None
        
        # Compare zoom level
        if abs(state1.get('zoom', 0) - state2.get('zoom', 0)) > 0.01:
            return True
        
        # Compare center position (with small tolerance for floating point)
        center1 = state1.get('center', [0, 0])
        center2 = state2.get('center', [0, 0])
        if abs(center1[0] - center2[0]) > 0.1 or abs(center1[1] - center2[1]) > 0.1:
            return True
        
        # Compare annotations
        annos1 = state1.get('annotations', [])
        annos2 = state2.get('annotations', [])
        
        # Different number of annotations
        if len(annos1) != len(annos2):
            return True
        
        # Compare each annotation
        for a1, a2 in zip(annos1, annos2):
            # Different type
            if a1.get('type') != a2.get('type'):
                return True
            
            # Different style
            if a1.get('color') != a2.get('color') or a1.get('weight') != a2.get('weight'):
                return True
            
            # Different coordinates
            coords1 = a1.get('coordinates', [])
            coords2 = a2.get('coordinates', [])
            if len(coords1) != len(coords2):
                return True
            
            # For polylines, check if coordinates are different
            # (allow small tolerance for floating point differences)
            for c1, c2 in zip(coords1, coords2):
                if abs(c1[0] - c2[0]) > 0.001 or abs(c1[1] - c2[1]) > 0.001:
                    return True
        
        # No changes detected
        return False
    
    def _on_annotation_data_change(self, event):
        """Handle when annotation_data is populated from JavaScript"""
        try:
            if not event.new or event.new == event.old:
                return
            
            annotation_json = json.loads(event.new)
            
            # Check if this is a manual save request
            if hasattr(self, '_manual_save_pending') and self._manual_save_pending:
                self._complete_manual_save(annotation_json)
                return
            
            # CRITICAL: If we're loading a state, just update last_saved_state and return
            # This prevents the loaded state from being saved as a new file
            if self._is_loading_state:
                logger.info("🔄 State loaded during navigation - updating reference without saving")
                self.last_saved_state = annotation_json
                self._is_loading_state = False  # Clear the flag
                return
            
            # Live tracking logic: only save if changed
            
            # First time - save initial state
            if not self.initial_state_saved:
                logger.info("💾 Saving initial state")
                self._save_live_tracking_state(annotation_json)
                self.last_saved_state = annotation_json
                self.initial_state_saved = True
                return
            
            # Compare with last saved state
            if self._compare_states(annotation_json, self.last_saved_state):
                logger.info("✏️  View changed - saving new state")
                self._save_live_tracking_state(annotation_json)
                self.last_saved_state = annotation_json
            else:
                # No changes - skip saving
                pass
            
        except Exception as e:
            logger.error(f"Error in annotation data change handler: {e}")
    
    def _save_live_tracking_state(self, annotation_json):
        """Save a live tracking state to disk"""
        try:
            #annotation_json['image_name'] = self.image_name
            annotation_json['image_dimensions'] = {
                'width': self.dimensions[0],
                'height': self.dimensions[1]
            }
            
            filename = f"{self.live_tracking_index:05d}.json"

            filepath = os.path.join(self.live_dir, filename)
            cached_filepath = str(cache.get(cache_key)).replace(".svs","")
            print(f"11111: {filepath} 21111: {cached_filepath}")
            save_annotation_json(filepath, annotation_json)
            
            # Update current index to track the latest save
            self.current_live_index = self.live_tracking_index
            
            # Increment for next save
            self.live_tracking_index += 1
            
            # Cleanup old files
            cleanup_old_live_tracking(self.live_dir, max_files=1000)
            
            logger.info(f"✓ Live tracking saved: {filename}")
            
        except Exception as e:
            logger.error(f"Error saving live tracking state: {e}")
    
    def _recenter_map(self, event=None):
        """Reset map to initial view (center + zoom 0)"""
        try:
            logger.info("🎯 Recentering map to initial view...")
            
            # Get initial view parameters from metadata
            metadata_path = f"/data/dzi_output/{self.image_name}_metadata.json"
            metadata = load_metadata(metadata_path)
            
            #start_level = metadata.get('recommended_start_level', 9)
            start_level = 8
            center_offset_y = metadata.get('center_offset_y', -1.15)
            
            # Calculate center coordinates (same as initial view)
            dzi_levels = metadata.get('dzi_levels', 18)
            scaleAtStart = 2 ** (dzi_levels - 1 - start_level)
            widthAtStartLevel = self.dimensions[0] / scaleAtStart
            heightAtStartLevel = self.dimensions[1] / scaleAtStart
            
            centerY = heightAtStartLevel / 2
            centerX = widthAtStartLevel / 2
            adjustedCenterY = centerY * center_offset_y
            
            # Create annotation data with reset view
            reset_data = {
                'image_name': self.image_name,
                'zoom': 0,  # Reset to zoom level 0
                'center': [adjustedCenterY, centerX],
                'annotations': [],  # Will be populated by JavaScript
                'timestamp': datetime.now().isoformat()
            }
            
            # Load the reset view (JavaScript will preserve existing annotations)
            self.viewer.annotation_data = json.dumps(reset_data)
            self.viewer.load_annotation_trigger += 1
            
            # Reset saved views counter since we're not loading from saved views
            self.current_saved_index = -1
            self._update_saved_views_counter()
            
            logger.info(f"✓ Map recentered to: zoom=0, center=[{adjustedCenterY:.1f}, {centerX:.1f}]")
            
        except Exception as e:
            logger.error(f"Error recentering map: {e}")
    
    def _toggle_minimap(self, event=None):
        """Toggle minimap visibility via JavaScript"""
        try:
            logger.info("🗺️  Toggling minimap visibility...")
            
            # Send special action to JavaScript via annotation_data
            self.viewer.annotation_data = json.dumps({
                'action': 'toggle_minimap',
                'timestamp': datetime.now().isoformat()
            })
            
            # Trigger the load annotation handler which will execute the toggle
            self.viewer.load_annotation_trigger += 1
            
            logger.info("✓ Minimap toggle triggered")
            
        except Exception as e:
            logger.error(f"Error toggling minimap: {e}")
    
    def _mark_done(self, event=None):
        """Toggle Done status (Done=True sets Ink=False, Done=False sets Ink=False)"""
        try:
            logger.info("✓ Toggling done status...")
            
            # Toggle done status
            self.done_status = not self.done_status
            
            # When Done is toggled to True, set Ink Found to False (no ink)
            # When Done is toggled to False, also set Ink Found to False (blank state)
            if self.done_status:
                # Done=True, Ink=False (Done with no ink)
                self.ink_found_status = False
            else:
                # Done=False, Ink=False (To Do state, blank ink status)
                self.ink_found_status = False
            
            # Save to JSON file
            save_ink_status(
                self.image_name,
                done=self.done_status,
                ink_found=self.ink_found_status
            )
            
            # Update button styling and status title in parent app
            if self.parent_app:
                self.parent_app._update_status_buttons()
                self.parent_app._update_status_title()
            
            logger.info(f"✓ Done status: done={self.done_status}, ink_found={self.ink_found_status}")
            
        except Exception as e:
            logger.error(f"Error marking done: {e}")
    
    def _mark_ink_found(self, event=None):
        """Mark current image as having ink found - toggles between all true and all false"""
        try:
            logger.info("🖊️  Toggling ink found status...")
            
            # If ink_found is already true, set both to false
            # Otherwise, set both to true
            if self.ink_found_status:
                #self.done_status = False
                self.ink_found_status = False
                logger.info("✓ Ink found status: OFF (both statuses set to false)")
            else:
                #self.done_status = True
                self.ink_found_status = True
                logger.info("✓ Ink found status: ON (both statuses set to true)")
            
            # Save to JSON file
            save_ink_status(
                self.image_name,
                done=self.done_status,
                ink_found=self.ink_found_status
            )
            
            # Update button styling and status title in parent app
            if self.parent_app:
                self.parent_app._update_status_buttons()
                self.parent_app._update_status_title()
            
        except Exception as e:
            logger.error(f"Error marking ink found: {e}")
    
    def _undo_annotation(self, event=None):
        """Load previous live tracking state (undo) - go back one file"""
        try:
            # Get all existing live tracking files
            existing_files = glob.glob(os.path.join(self.live_dir, "*.json"))
            if not existing_files:
                logger.info("No live tracking files available")
                return
            
            # Get file numbers
            file_numbers = []
            for f in existing_files:
                basename = os.path.basename(f)
                try:
                    num = int(basename.replace('.json', ''))
                    file_numbers.append(num)
                except ValueError:
                    continue
            
            if not file_numbers:
                logger.info("No valid live tracking files")
                return
            
            file_numbers.sort()
            
            # If current_live_index is -1 or not in list, start from the latest
            if self.current_live_index == -1 or self.current_live_index not in file_numbers:
                self.current_live_index = file_numbers[-1]
            
            # Find current position and go back one
            try:
                current_pos = file_numbers.index(self.current_live_index)
                if current_pos > 0:
                    # CRITICAL: Set navigation flags BEFORE loading
                    self._is_loading_state = True
                    self._navigation_timestamp = time.time()
                    
                    # Go to previous file
                    prev_index = file_numbers[current_pos - 1]
                    filename = f"{prev_index:05d}.json"
                    filepath = os.path.join(self.live_dir, filename)
                    
                    annotation_json = load_annotation_json(filepath)
                    if annotation_json:
                        # Load the state into viewer
                        self.viewer.annotation_data = json.dumps(annotation_json)
                        self.viewer.load_annotation_trigger += 1
                        self.current_live_index = prev_index
                        
                        # Update last saved state reference (will also be updated in _on_annotation_data_change)
                        self.last_saved_state = annotation_json
                        
                        # Reset saved views counter since we're loading from live tracking
                        self.current_saved_index = -1
                        self._update_saved_views_counter()
                        
                        logger.info(f"⟲ Undo: Loaded {filename} (state {current_pos}/{len(file_numbers)-1})")
                else:
                    logger.info("Already at the first live tracking state")
            except ValueError:
                logger.info("Current index not found in file list")
            
        except Exception as e:
            logger.error(f"Error in undo: {e}")
            self._is_loading_state = False  # Clear flag on error
    
    def _redo_annotation(self, event=None):
        """Load next live tracking state (redo) - go forward one file"""
        try:
            # Get all existing live tracking files
            existing_files = glob.glob(os.path.join(self.live_dir, "*.json"))
            if not existing_files:
                logger.info("No live tracking files available for redo")
                return
            
            # Get file numbers
            file_numbers = []
            for f in existing_files:
                basename = os.path.basename(f)
                try:
                    num = int(basename.replace('.json', ''))
                    file_numbers.append(num)
                except ValueError:
                    continue
            
            if not file_numbers:
                logger.info("No valid live tracking files")
                return
            
            file_numbers.sort()
            
            # Find current position and go forward one
            try:
                current_pos = file_numbers.index(self.current_live_index)
                if current_pos < len(file_numbers) - 1:
                    # CRITICAL: Set navigation flags BEFORE loading
                    self._is_loading_state = True
                    self._navigation_timestamp = time.time()
                    
                    # Go to next file
                    next_index = file_numbers[current_pos + 1]
                    filename = f"{next_index:05d}.json"
                    filepath = os.path.join(self.live_dir, filename)
                    
                    annotation_json = load_annotation_json(filepath)
                    if annotation_json:
                        # Load the state into viewer
                        self.viewer.annotation_data = json.dumps(annotation_json)
                        self.viewer.load_annotation_trigger += 1
                        self.current_live_index = next_index
                        
                        # Update last saved state reference
                        self.last_saved_state = annotation_json
                        
                        # Reset saved views counter since we're loading from live tracking
                        self.current_saved_index = -1
                        self._update_saved_views_counter()
                        
                        logger.info(f"⟳ Redo: Loaded {filename} (state {current_pos+2}/{len(file_numbers)})")
                else:
                    logger.info("Already at the latest live tracking state")
            except ValueError:
                logger.info("Current index not found in file list")
            
        except Exception as e:
            logger.error(f"Error in redo: {e}")
            self._is_loading_state = False  # Clear flag on error
    
    def _save_current_view(self, event=None):
        """Save current view to saved_views"""
        try:
            # Set flag to indicate this is a manual save
            self._manual_save_pending = True
            
            # When saving, mark both done=True and ink_found=True
            self.done_status = True
            self.ink_found_status = True
            
            # Save ink status
            save_ink_status(
                self.image_name,
                done=self.done_status,
                ink_found=self.ink_found_status
            )
            
            # Update button styling in parent app
            if self.parent_app:
                self.parent_app._update_status_buttons()
                self.parent_app._update_status_title()
            
            logger.info(f"✓ Save: Set done=True, ink_found=True")
            
            # Trigger JavaScript to get current annotations
            self.viewer.save_annotation_trigger += 1
            
            # The actual save will happen in _on_annotation_data_change
            # after JavaScript populates annotation_data
            
        except Exception as e:
            logger.error(f"Error triggering save view: {e}")
    
    def _complete_manual_save(self, annotation_json):
        """Complete a manual save operation"""
        try:
            # Add image metadata
            annotation_json['image_name'] = self.image_name
            annotation_json['image_dimensions'] = {
                'width': self.dimensions[0],
                'height': self.dimensions[1]
            }
            annotation_json['saved_at'] = datetime.now().isoformat()
            
            # Get next saved view number
            saved_views = get_saved_views_list(self.saved_dir)
            next_num = saved_views[-1][0] + 1 if saved_views else 0
            
            filename = f"{next_num:05d}.json"
            filepath = os.path.join(self.saved_dir, filename)
            save_annotation_json(filepath, annotation_json)
            
            # Update saved views list
            self.saved_views = get_saved_views_list(self.saved_dir)
            #self.current_saved_index = len(self.saved_views) - 1
            
            logger.info(f"✓ Saved view {filename}")
            
            # Update counter display
            self._update_saved_views_counter()
            
            self._manual_save_pending = False
            
        except Exception as e:
            logger.error(f"Error completing manual save: {e}")
            self._manual_save_pending = False
    
    def _update_saved_views_counter(self):
        """Update saved views counter display"""
        try:
            self.saved_views = get_saved_views_list(self.saved_dir)
            total_views = len(self.saved_views)
            # current_saved_index is 0-based, display as 1-based (or 0 if no view loaded)
            current_num = self.current_saved_index + 1 if self.current_saved_index >= 0 else 0
            
            if self.parent_app and hasattr(self.parent_app, 'saved_views_counter'):
                #self.parent_app.saved_views_counter.object = f"**Reloaded {current_num}/{total_views}**"
                self.parent_app.saved_views_counter.object = f"**Saved: {total_views}**"
                logger.info(f"Updated saved views counter: {current_num}/{total_views}")
        except Exception as e:
            logger.error(f"Error updating saved views counter: {e}")
    
    def _load_prev_saved(self, event=None):
        """Load previous saved view"""
        try:
            self.saved_views = get_saved_views_list(self.saved_dir)
            
            if not self.saved_views:
                logger.info("No saved views available")
                self._update_saved_views_counter()
                return
            
            # Move to previous
            if self.current_saved_index > 0:
                self.current_saved_index -= 1
            else:
                self.current_saved_index = 0
                logger.info("Already at first saved view")
                self._update_saved_views_counter()
                return
            
            # CRITICAL: Set navigation flags BEFORE loading
            self._is_loading_state = True
            self._navigation_timestamp = time.time()
            
            # Load the view
            _, filepath = self.saved_views[self.current_saved_index]
            annotation_json = load_annotation_json(filepath)
            
            if annotation_json:
                self.viewer.annotation_data = json.dumps(annotation_json)
                self.viewer.load_annotation_trigger += 1
                self.last_saved_state = annotation_json
                logger.info(f"◀ Loaded previous saved view: {os.path.basename(filepath)}")
                self._update_saved_views_counter()
            
        except Exception as e:
            logger.error(f"Error loading previous saved view: {e}")
            self._is_loading_state = False  # Clear flag on error
    
    def _load_next_saved(self, event=None):
        """Load next saved view"""
        try:
            self.saved_views = get_saved_views_list(self.saved_dir)
            
            if not self.saved_views:
                logger.info("No saved views available")
                self._update_saved_views_counter()
                return
            
            # Move to next
            if self.current_saved_index < len(self.saved_views) - 1:
                self.current_saved_index += 1
            else:
                self.current_saved_index = len(self.saved_views) - 1
                logger.info("Already at last saved view")
                self._update_saved_views_counter()
                return
            
            # CRITICAL: Set navigation flags BEFORE loading
            self._is_loading_state = True
            self._navigation_timestamp = time.time()
            
            # Load the view
            _, filepath = self.saved_views[self.current_saved_index]
            annotation_json = load_annotation_json(filepath)
            
            if annotation_json:
                self.viewer.annotation_data = json.dumps(annotation_json)
                self.viewer.load_annotation_trigger += 1
                self.last_saved_state = annotation_json
                logger.info(f"▶ Loaded next saved view: {os.path.basename(filepath)}")
                self._update_saved_views_counter()
            
        except Exception as e:
            logger.error(f"Error loading next saved view: {e}")
            self._is_loading_state = False  # Clear flag on error
    
    def _on_keyboard_shortcut(self, event):
        """Handle keyboard shortcuts from JavaScript"""
        try:
            shortcut = event.new
            if not shortcut:
                return
            
            logger.info(f"⌨️  Keyboard shortcut: {shortcut}")
            
            if shortcut == 'undo':
                self._undo_annotation()
            elif shortcut == 'redo':
                self._redo_annotation()
            elif shortcut == 'save':
                self._save_current_view()
            elif shortcut == 'prev':
                self._load_prev_saved()
            elif shortcut == 'next':
                self._load_next_saved()
            elif shortcut == 'recenter':
                self._recenter_map()
            elif shortcut == 'prev_image':
                # Trigger prev image in InteractiveSVSApp if available
                if hasattr(self, 'parent_app'):
                    self.parent_app._load_prev_image()
            elif shortcut == 'next_image':
                # Trigger next image in InteractiveSVSApp if available
                if hasattr(self, 'parent_app'):
                    self.parent_app._load_next_image()
            elif shortcut == 'toggle_minimap':
                # Toggle minimap via JavaScript
                self._toggle_minimap()
            elif shortcut == 'done':
                self._mark_done()
            # ink_found shortcut removed - button is disabled and only updated by Done/Save
            
            # Reset trigger
            self.viewer.keyboard_trigger = ''
            
        except Exception as e:
            logger.error(f"Error handling keyboard shortcut: {e}")
    
    def create_dashboard(self):
        # Common tooltip stylesheet for all buttons
        tooltip_style = """
            :host(.solid) .bk-btn {
                position: relative;
            }
            :host(.solid) .bk-btn::after {
                content: attr(title);
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
        """
        
        # Create recenter button
        recenter_button = pn.widgets.Button(
            name='Reset View',
            button_type='default',
            width=120,
            height=35,
            margin=(5, 5),
            stylesheets=["""  
            :host(.solid) .bk-btn {
                background-color: #17a2b8 !important;
                color: #ffffff !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 16px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #1fc8e3 !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Ctrl+R / Cmd+R';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        recenter_button.on_click(self._recenter_map)
        
        # Create control buttons with inline styling using stylesheets
        undo_button = pn.widgets.Button(
            name='⟲ UNDO',
            button_type='default',
            width=80,
            height=35,
            margin=(5, 5),
            stylesheets=["""
            :host(.solid) .bk-btn {
                background-color: #ffc107 !important;
                color: #000000 !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 13px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #ffcd39 !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Ctrl+Z / Cmd+Z';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        undo_button.on_click(self._undo_annotation)
        
        redo_button = pn.widgets.Button(
            name='⟳ REDO',
            button_type='default',
            width=80,
            height=35,
            margin=(5, 5),
            stylesheets=["""
            :host(.solid) .bk-btn {
                background-color: #ffc107 !important;
                color: #000000 !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 13px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #ffcd39 !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Ctrl+A / Cmd+A';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        redo_button.on_click(self._redo_annotation)
        
        save_button = pn.widgets.Button(
            name='💾 Save',
            button_type='default',
            width=80,
            height=35,
            margin=(5, 5),
            stylesheets=["""
            :host(.solid) .bk-btn {
                background-color: #28a745 !important;
                color: #ffffff !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 13px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #34ce57 !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Key "S" (Done + Ink Found)';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        save_button.on_click(self._save_current_view)
        
        prev_button = pn.widgets.Button(
            name='◀ ',
            button_type='default',
            width=40,
            height=35,
            margin=(5, 5),
            stylesheets=["""
            :host(.solid) .bk-btn {
                background-color: #007bff !important;
                color: #ffffff !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 13px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #0d8aff !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Ctrl+← / Cmd+←';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        prev_button.on_click(self._load_prev_saved)
        
        next_button = pn.widgets.Button(
            name=' ▶',
            button_type='default',
            width=40,
            height=35,
            margin=(5, 5),
            stylesheets=["""
            :host(.solid) .bk-btn {
                background-color: #007bff !important;
                color: #ffffff !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 13px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                position: relative;
            }
            :host(.solid) .bk-btn:hover {
                background-color: #0d8aff !important;
                box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
            }
            :host(.solid) .bk-btn::after {
                content: 'Ctrl+→ / Cmd+→';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 8px;
                padding: 6px 10px;
                background-color: #000000;
                color: #ffffff;
                font-size: 11px;
                font-weight: normal;
                white-space: nowrap;
                border-radius: 4px;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            :host(.solid) .bk-btn:hover::after {
                opacity: 1;
            }
            """]
        )
        next_button.on_click(self._load_next_saved)
        
        # Create modal placeholder HTML that will be in the initial template
        # Must NOT use width=0 height=0 as Panel may not render those
        modal_placeholder_html = pn.pane.HTML(
            """
            <div id="settings-backdrop"></div>
            <div id="settings-modal-wrapper-container"></div>
            """,
            sizing_mode='stretch_width',
            height=0,
            margin=0
        )
        
        # Create layout without sidebar - INCLUDE modal placeholder in initial main list
        template = pn.template.FastListTemplate(
            title="",  # Empty title
            sidebar=[],  # Empty sidebar
            main=[self.viewer, modal_placeholder_html],  # Add placeholder to initial template
            header_background="#170f90",
            sidebar_width=0,  # Hide sidebar completely
            theme_toggle=False,  # Remove theme toggle button
            busy_indicator=None
        )
        
        # Add buttons to header
        self.button_row_live_tracking = pn.Row(
            recenter_button,
            undo_button,
            redo_button,
            sizing_mode='fixed',
            align='center'
            )
        #template.header.append(self.button_row_live_tracking)
        
        self.button_row_saved_views = pn.Row(
            pn.layout.HSpacer(width=100),
            #prev_button,
            save_button,
            #next_button,
            sizing_mode='fixed',
            align='center'
        )
        
        # Store button references for keyboard shortcuts
        self.undo_button = undo_button
        self.redo_button = redo_button
        self.save_button = save_button
        self.prev_button = prev_button
        self.next_button = next_button
        
        # Watch for keyboard triggers from viewer
        self.viewer.param.watch(self._on_keyboard_shortcut, 'keyboard_trigger')
        
        return template


# Simpler approach: Create a function that returns the dashboard based on selection


# Create interactive application with image selector
class InteractiveSVSApp:
    """Interactive SVS viewer with image selection"""
    
    def __init__(self):
        print("=" * 80, flush=True)
        print("🚀 InteractiveSVSApp.__init__() starting", flush=True)
        print("=" * 80, flush=True)
        print("XYZABC123 TEST MARKER - CODE VERSION 2.0", flush=True)
        print("DEBUG: About to init logger messages", flush=True)
        logger.info("=" * 80)
        logger.info("🚀 InteractiveSVSApp.__init__() starting")
        logger.info("=" * 80)
        logger.info("XYZABC123 TEST MARKER - CODE VERSION 2.0")
        print("DEBUG: About to create KeyboardShortcutManager", flush=True)
        
        # Initialize keyboard shortcuts manager
        self.shortcut_manager = KeyboardShortcutManager()
        print("DEBUG: KeyboardShortcutManager created successfully", flush=True)
        logger.info("Keyboard shortcuts manager initialized")
        print("DEBUG: About to call get_available_images", flush=True)
        
        self.available_images = get_available_images()
        self.current_tool = None
        self.current_image_index = 0  # Track current image index
        
        print(f"Found {len(self.available_images)} available images", flush=True)
        logger.info(f"Found {len(self.available_images)} available images")
        
        # Create image selector
        print("DEBUG: Creating image_options dictionary", flush=True)
        image_options = {img['display_name']: img['svs_path'] for img in self.available_images}
        print(f"DEBUG: image_options created with {len(image_options)} items", flush=True)
        logger.info(f"Image options: {list(image_options.keys())}")
        
        print("DEBUG: Checking if image_options is empty", flush=True)
        if not image_options:
            print("DEBUG: NO IMAGES - entering if block", flush=True)
            logger.error("No DZI images found!")
            self.image_selector = pn.pane.Markdown("**No images available.**")
            self.template = pn.template.FastListTemplate(
                title="Magic Annotation Tool",
                sidebar=[pn.pane.Markdown("Run: `docker exec ink_annotation_tool python /app/convert_to_dzi.py`")]
            )
        else:
            print("DEBUG: Images found - entering else block", flush=True)
            # Default to first available image
            image_name_in_cache = cache.get(cache_key)

            if image_name_in_cache:
                self.current_image_index = self.get_image_index_by_name(image_name_in_cache)
                
            else:
                self.current_image_index = 0

            default_image = list(image_options.values())[self.current_image_index]
            
            self.image_selector = pn.widgets.Select(
                name='Select',
                options=image_options,
                value=default_image,
                width=50,
                height=35,
                margin=(5, 10)
            )


            # Create Previous Image button
            self.prev_image_button = pn.widgets.Button(
                name='◀',
                button_type='default',
                width=40,
                height=35,
                margin=(10, 10),
                stylesheets=["""
                :host(.solid) .bk-btn {
                    background-color: #6c757d !important;
                    color: #ffffff !important;
                    border: 2px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 14px !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 6px 10px;
                    margin-top: 54px;
                    position: relative;
                }
                :host(.solid) .bk-btn:hover {
                    background-color: #5a6268 !important;
                    box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
                }
                :host(.solid) .bk-btn:disabled {
                    background-color: #cccccc !important;
                    color: #666666 !important;
                    cursor: not-allowed !important;
                }
                :host(.solid) .bk-btn::after {
                    content: 'Key "←"';
                    position: absolute;
                    top: 100%;
                    left: 50%;
                    transform: translateX(-50%);
                    margin-top: 8px;
                    padding: 6px 10px;
                    background-color: #000000;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: normal;
                    white-space: nowrap;
                    border-radius: 4px;
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s;
                    z-index: 10000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                }
                :host(.solid) .bk-btn:hover::after {
                    opacity: 1;
                }
                """]
            )
            self.prev_image_button.on_click(self._load_prev_image)

            # Create image index input box using TextInput (easier to style than IntInput)
            self.image_index_input = pn.widgets.TextInput(
                name='',
                value=str(self.current_image_index + 1),
                width=55,
                height=35,
                margin=(10, 10),
                css_classes=['custom-number-input'],
                stylesheets=["""
                :host {
                    --design-background-text-color: #000000;
                }
                input {
                    background-color: #ffc107 !important;
                    color: #000000 !important;
                    border: 3px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 16px !important;
                    text-align: center !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 6px 10px !important;
                    margin-top: 24px !important;
                }
                input:focus {
                    background-color: #ffc107 !important;
                    color: #000000 !important;
                    outline: 2px solid #ffffff !important;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.6) !important;
                }
                """]
            )

            # Add callback for input box
            self.image_index_input.param.watch(self._on_index_text_change, 'value')

            # Create Next Image button
            self.next_image_button = pn.widgets.Button(
                name='▶',
                button_type='default',
                width=40,
                height=35,
                margin=(10, 10),
                stylesheets=["""
                :host(.solid) .bk-btn {
                    background-color: #6c757d !important;
                    color: #ffffff !important;
                    border: 2px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 14px !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 6px 10px;
                    margin-top: 54px;
                    position: relative;
                }
                :host(.solid) .bk-btn:hover {
                    background-color: #5a6268 !important;
                    box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
                }
                :host(.solid) .bk-btn:disabled {
                    background-color: #cccccc !important;
                    color: #666666 !important;
                    cursor: not-allowed !important;
                }
                :host(.solid) .bk-btn::after {
                    content: 'Key "→"';
                    position: absolute;
                    top: 100%;
                    left: 50%;
                    transform: translateX(-50%);
                    margin-top: 8px;
                    padding: 6px 10px;
                    background-color: #000000;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: normal;
                    white-space: nowrap;
                    border-radius: 4px;
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s;
                    z-index: 10000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                }
                :host(.solid) .bk-btn:hover::after {
                    opacity: 1;
                }
                """]
            )
            self.next_image_button.on_click(self._load_next_image)

            # Update button states
            self._update_navigation_buttons()

            # Add a text display for the current image name with smart truncation
            current_image_name = os.path.basename(default_image).replace('.svs', '')
            
            # Smart truncation - show start and end of name
            max_display_length = 60
            if len(current_image_name) > max_display_length:
                # Show first 30 and last 25 chars with ... in middle
                display_name = current_image_name[:30] + '...' + current_image_name[-25:]
            else:
                display_name = current_image_name
            
            self.image_name_display = pn.pane.Markdown(
                f"**Image:** {display_name}",
                styles={
                    'font-size': '14px',
                    'font-weight': 'bold',
                    'color': '#ffffff',
                    'margin-top': '34px !important',
                    'white-space': 'nowrap',
                    'overflow': 'hidden',
                    'text-overflow': 'ellipsis',
                    'max-width': '400px'
                },
                width=400,
                margin=(20, 10),
                css_classes=['image-name-tooltip']
            )

            # Add a text display for the current image name
            self.image_total_num_display = pn.pane.Markdown(
                 f"Total: {len(self.available_images)}",
                styles={
                    'font-size': '16px',
                    'font-weight': 'bold',
                    'color': '#ffffff',
                    'margin-top': '64px !important'
                },
                width=42,
                margin=(5, 10)
            )
            
            # Add status count display
            done_count, ink_found_count = get_status_counts()
            self.status_title = pn.pane.Markdown(
                f"**Total: Done: {done_count} Ink Images: {ink_found_count}**",
                styles={
                    'font-size': '15px',
                    'font-weight': 'bold',
                    'color': '#ffffff',
                },
                width=100,
                margin=(5, 10)
            )
            
            # Create Done button with dynamic styling
            self.done_button = pn.widgets.Button(
                name='To Do',
                button_type='default',  # Start with default, will change dynamically
                width=90,
                height=35,
                margin=(10, 10),
                stylesheets=["""
                :host(.solid) .bk-btn {
                    background-color: #6c757d !important;
                    color: #ffffff !important;
                    border: 2px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 14px !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 6px 16px;
                    margin-top: 54px;
                    position: relative;
                }
                :host(.solid) .bk-btn:hover {
                    background-color: #5a6268 !important;
                    box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
                }
                :host(.solid) .bk-btn-success {
                    background-color: #28a745 !important;
                }
                :host(.solid) .bk-btn-success:hover {
                    background-color: #218838 !important;
                }
                :host(.solid) .bk-btn::after {
                    content: 'Key "D" (Done, no ink)';
                    position: absolute;
                    top: 100%;
                    left: 50%;
                    transform: translateX(-50%);
                    margin-top: 8px;
                    padding: 6px 10px;
                    background-color: #000000;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: normal;
                    white-space: nowrap;
                    border-radius: 4px;
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s;
                    z-index: 10000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                }
                :host(.solid) .bk-btn:hover::after {
                    opacity: 1;
                }
                """]
            )
            
            # Create Ink Found button with dynamic styling (disabled - only updated by Done/Save)
            self.ink_found_button = pn.widgets.Button(
                name='Ink Not Found',
                button_type='default',  # Start with default, will change dynamically
                width=130,
                height=35,
                margin=(10, 10),
                disabled=True,  # Disabled - only updated by Done/Save buttons
                stylesheets=["""
                :host(.solid) .bk-btn {
                    background-color: #6c757d !important;
                    color: #ffffff !important;
                    border: 2px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 14px !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 6px 16px;
                    margin-top: 54px;
                    position: relative;
                }
                :host(.solid) .bk-btn:hover {
                    background-color: #5a6268 !important;
                    box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
                }
                :host(.solid) .bk-btn-success {
                    background-color: #28a745 !important;
                }
                :host(.solid) .bk-btn-success:hover {
                    background-color: #218838 !important;
                }
                :host(.solid) .bk-btn::after {
                    content: 'Auto-updated by Done/Save';
                    position: absolute;
                    top: 100%;
                    left: 50%;
                    transform: translateX(-50%);
                    margin-top: 8px;
                    padding: 6px 10px;
                    background-color: #000000;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: normal;
                    white-space: nowrap;
                    border-radius: 4px;
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s;
                    z-index: 10000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                }
                :host(.solid) .bk-btn:hover::after {
                    opacity: 1;
                }
                """]
            )
            
            logger.info(f"Image selector created with default: {default_image}")
            
            # Create saved views counter display (app-level, persists across image changes)
            self.saved_views_counter = pn.pane.Markdown(
                "**Saved 0**",
                styles={
                    'font-size': '17px',
                    'font-weight': 'bold',
                    'color': '#ffffff',
                    'margin-top': '8px'
                },
                width=48,
                margin=(5, 5)
            )
            
            # Create help button with JavaScript alert
            self.help_button = pn.widgets.Button(
                name='❓',
                button_type='primary',
                width=30,
                height=30,
                margin=(22, 5),
                stylesheets=['''
                :host(.solid) .bk-btn {
                    background-color: #ffc107 !important;
                    color: #000000 !important;
                    border: 2px solid #ffffff !important;
                    font-weight: bold !important;
                    font-size: 12px !important;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                    padding: 2px 10px;
                    margin-top: 54px;
                    position: relative;
                }
                :host(.solid) .bk-btn:hover {
                    background-color: #ffcd39 !important;
                    box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
                }
                :host(.solid) .bk-btn::after {
                    content: 'Help (H)';
                    position: absolute;
                    top: 100%;
                    left: 50%;
                    transform: translateX(-50%);
                    margin-top: 8px;
                    padding: 6px 10px;
                    background-color: #000000;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: normal;
                    white-space: nowrap;
                    border-radius: 4px;
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s;
                    z-index: 10000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                }
                :host(.solid) .bk-btn:hover::after {
                    opacity: 1;
                }
                ''']
            )
            
            # Create HTML pane with JavaScript to show help modal
            self.help_trigger = pn.pane.HTML('', width=0, height=0)
            
            # Connect button handlers once (not per image load)
            self.done_button.on_click(self._on_done_click)
            self.ink_found_button.on_click(self._on_ink_found_click)
            self.help_button.on_click(self._show_help_modal)
            print("DEBUG: Button handlers connected", flush=True)
            
            # Create initial tool and store it
            print(f"DEBUG: About to load default image: {default_image}", flush=True)
            logger.info(f"Loading default image: {default_image}")
            self._load_image(default_image)
            print("DEBUG: Default image loaded successfully", flush=True)
            logger.info("✓ Default image loaded")
            
            # Create template
            logger.info("Creating template from current_tool...")
            self.template = self.current_tool.create_dashboard()
            logger.info("✓ Template created")

            # Add custom CSS for input box styling and settings modal
            logger.info("Adding custom CSS...")
            self.template.config.raw_css.append("""
            .custom-number-input input[type="text"] {
                background-color: #ffc107 !important;
                color: #000000 !important;
                border: 3px solid #ffffff !important;
                font-weight: bold !important;
                font-size: 14px !important;
                text-align: center !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
                padding: 6px 10px !important;
                margin-top: 54px !important;
            }
            .custom-number-input input[type="text"]:focus {
                background-color: #ffc107 !important;
                color: #000000 !important;
                outline: 2px solid #ffffff !important;
                box-shadow: 0 2px 8px rgba(0,0,0,0.6) !important;
            }
                                                
            /* Image name with tooltip */
            .image-name-tooltip {
                position: relative;
                cursor: help;
            }
            .image-name-tooltip:hover::after {
                content: attr(data-full-name);
                position: absolute;
                top: 100%;
                left: 0;
                margin-top: 5px;
                padding: 8px 12px;
                background-color: #000000;
                color: #ffffff;
                font-size: 12px;
                white-space: nowrap;
                border-radius: 4px;
                z-index: 10000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            }
            
            /* Settings Modal Styles */
            #settings-modal-placeholder {
                position: fixed !important;
                top: 50% !important;
                left: 50% !important;
                transform: translate(-50%, -50%) !important;
                z-index: 10000 !important;
                background: white !important;
                border-radius: 8px !important;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
                max-height: 90vh !important;
                max-width: 90vw !important;
                overflow: auto !important;
                display: none !important;
                width: 850px;
                padding: 20px;
            }
            #settings-modal-placeholder.show {
                display: block !important;
            }
            #settings-backdrop {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.6);
                z-index: 9998;
            }
            #settings-backdrop.show {
                display: block !important;
            }
            """)

            
            print("DEBUG: Template created from current_tool", flush=True)
            logger.info("Template created from current_tool")
            
            # Create settings button and modal
            print("DEBUG: About to create settings button and modal", flush=True)
            try:
                logger.info("Creating settings button and modal...")
                print("DEBUG: Calling create_settings_button_and_modal function", flush=True)
                self.settings_button, self.settings_modal = create_settings_button_and_modal(
                    self.shortcut_manager,
                    on_save_callback=self._on_shortcuts_saved
                )
                print(f"DEBUG: Settings button created: {self.settings_button}", flush=True)
                print(f"DEBUG: Settings modal created: {self.settings_modal}", flush=True)
                logger.info("✓ Settings button and modal created successfully")
            except Exception as e:
                print(f"DEBUG: Exception creating settings button: {e}", flush=True)
                logger.error(f"❌ Error creating settings button: {e}", exc_info=True)
                # Create a dummy button as fallback
                self.settings_button = pn.widgets.Button(name="⚙️", button_type="light", width=40, height=35)
                self.settings_modal = pn.Column(visible=False)
                print("DEBUG: Created fallback button", flush=True)
            
            # Add selector with Previous/Next buttons, then image name, status buttons, status title, then control buttons
            print("DEBUG: About to add elements to template header", flush=True)
            print(f"DEBUG: Settings button before adding to header: {self.settings_button}", flush=True)
            self.template.header.append(
                pn.Row(
                    self.current_tool.button_row_live_tracking,
                    pn.layout.HSpacer(),
                    pn.Column(self.image_name_display),
                    pn.layout.HSpacer(),
                    pn.Column(self.status_title), 
                    pn.layout.HSpacer(),                
                    self.ink_found_button, 
                    self.done_button,
                    pn.layout.HSpacer(),
                    self.prev_image_button,
                    self.image_index_input,
                    self.next_image_button,
                    self.image_total_num_display,
                    
                    #self.image_selector,
                    
                    pn.layout.HSpacer(),
                    self.current_tool.button_row_saved_views,
                    self.saved_views_counter,
                    pn.layout.HSpacer(width=20),
                    self.help_button,
                    #self.settings_button,
                    sizing_mode='scale_width',
                    align='center'
                )
            )
            print("DEBUG: Elements added to template header successfully", flush=True)
            
            # Add help trigger to main
            print("DEBUG: About to add help_trigger to main", flush=True)
            self.template.main.append(self.help_trigger)
            
            # Add the actual modal content (placeholders already in template from create_dashboard)
            print("DEBUG: Adding modal content", flush=True)
            self.template.main.append(self.settings_modal)
            print(f"DEBUG: Modal content added", flush=True)
            
            logger.info(f"Image selector with navigation buttons added to header")
            print("DEBUG: Header setup complete", flush=True)
            
            # Store reference to parent app in current_tool for keyboard shortcuts
            self.current_tool.parent_app = self
            
            # Watch for changes
            self.image_selector.param.watch(self._on_selection_change, 'value')
            logger.info("✓ Callback registered on image_selector.value parameter")
            logger.info("=" * 80)
    
    def get_image_index_by_name(self, image_name):
        """
        Get numeric index (0, 1, 2, ...) for a given image name.
        
        Args:
            image_name (str): Image name (e.g., 'BRACS_1579' or 'BRACS_1579.svs')
        
        Returns:
            int: Numeric index, or None if not found
        """
        available_images = self.available_images
        
        # Remove .svs extension if present
        search_name = image_name.replace('.svs', '')
        
        # Find the image by name
        for idx, img in enumerate(available_images):
            if img['name'] == search_name:
                return idx
        
        return 0
    
    def _on_shortcuts_saved(self):
        """Callback when keyboard shortcuts are saved"""
        logger.info("Keyboard shortcuts saved - user should refresh to apply changes")
    

    def _update_navigation_buttons(self):
        """Update the enabled/disabled state of navigation buttons"""
        # Disable Previous button if at first image
        self.prev_image_button.disabled = (self.current_image_index <= 0)
        
        # Disable Next button if at last image
        self.next_image_button.disabled = (self.current_image_index >= len(self.available_images) - 1)

        # Update index input to current position (use string for TextInput)
        if hasattr(self, 'image_index_input'):
            self.image_index_input.value = str(self.current_image_index + 1)

    def _load_prev_image(self, event=None):
        """Load the previous image in the list"""
        if self.current_image_index > 0:
            self.current_image_index -= 1
            new_image_path = self.available_images[self.current_image_index]['svs_path']
            
            logger.info(f"◀ Loading previous image: {os.path.basename(new_image_path)}")
            
            # Update selector (this will trigger _on_selection_change)
            self.image_selector.value = new_image_path
            
            # Update button states
            self._update_navigation_buttons()

    def _load_next_image(self, event=None):
        """Load the next image in the list"""
        if self.current_image_index < len(self.available_images) - 1:
            self.current_image_index += 1
            new_image_path = self.available_images[self.current_image_index]['svs_path']
            
            logger.info(f"▶ Loading next image: {os.path.basename(new_image_path)}")
            
            # Update selector (this will trigger _on_selection_change)
            self.image_selector.value = new_image_path
            
            # Update button states
            self._update_navigation_buttons()

    def _on_index_text_change(self, event):
        """Load image by direct text input"""
        try:
            # Convert text to integer
            requested_index = int(event.new) - 1
            
            # Validate range
            if requested_index < 0 or requested_index >= len(self.available_images):
                logger.warning(f"Invalid index: {event.new} (valid range: 1-{len(self.available_images)})")
                # Reset to current valid index
                self.image_index_input.value = str(self.current_image_index + 1)
                return
            
            # Only load if different from current
            if requested_index != self.current_image_index:
                self.current_image_index = requested_index
                new_image_path = self.available_images[self.current_image_index]['svs_path']
                
                logger.info(f"🔢 Loading image by index: {event.new} ({os.path.basename(new_image_path)})")
                
                # Update selector (this will trigger _on_selection_change)
                self.image_selector.value = new_image_path
                
                # Update button states
                self._update_navigation_buttons()
        except ValueError:
            logger.warning(f"Invalid input: {event.new} (must be a number)")
            # Reset to current valid index
            self.image_index_input.value = str(self.current_image_index + 1)
        except Exception as e:
            logger.error(f"Error loading image by index: {e}")
            # Reset to current valid index
            self.image_index_input.value = str(self.current_image_index + 1)

    
    def _load_image(self, svs_path):
        """Load a new image and create new tool instance"""
        logger.info(f"Loading image: {svs_path}")
        
        # Find the image dictionary to get dzi_path
        dzi_path = None
        for img in self.available_images:
            if img['svs_path'] == svs_path:
                dzi_path = img.get('dzi_path')
                break
        
        # Create new tool instance (it will load its own metadata)
        self.current_tool = SVSAnnotationTool(svs_path, dzi_path=dzi_path, shortcut_manager=self.shortcut_manager)
        
        # Link parent app to tool for keyboard shortcuts
        self.current_tool.parent_app = self
        
        # Update button styles based on initial status
        self._update_status_buttons()
        
        # Update saved views counter
        self.current_tool._update_saved_views_counter()
        
        # Update saved views counter
        self.current_tool._update_saved_views_counter()
    
    def _on_done_click(self, event):
        """Handle Done button click"""
        if self.current_tool:
            self.current_tool._mark_done()
    
    def _on_ink_found_click(self, event):
        """Handle Ink Found button click"""
        if self.current_tool:
            self.current_tool._mark_ink_found()
    
    def _update_status_buttons(self, event=None):
        """Update button styling and text based on status"""
        if not self.current_tool:
            return
        
        # Update Done button style and text
        if self.current_tool.done_status:
            self.done_button.button_type = 'success'
            self.done_button.name = 'Done'
        else:
            self.done_button.button_type = 'default'
            self.done_button.name = 'To Do'
        
        # Update Ink Found button style and text based on three states:
        # 1. Done=False → blank/hidden (show empty text)
        # 2. Done=True, Ink=False → "Ink Not Found"
        # 3. Done=True, Ink=True → "Ink Found"
        if not self.current_tool.done_status:
            # State 1: To Do (blank ink status)
            self.ink_found_button.button_type = 'default'
            self.ink_found_button.name = ''  # Blank
        elif self.current_tool.ink_found_status:
            # State 3: Done with ink found
            self.ink_found_button.button_type = 'success'
            self.ink_found_button.name = 'Ink Found'
        else:
            # State 2: Done without ink
            self.ink_found_button.button_type = 'success'
            self.ink_found_button.name = 'Ink Not Found'
        
        logger.info(f"Updated status buttons: done={self.current_tool.done_status} ({self.done_button.name}), ink_found={self.current_tool.ink_found_status} ({self.ink_found_button.name})")
    
    def _update_status_title(self):
        """Update status title with current counts"""
        done_count, ink_found_count = get_status_counts()
        self.status_title.object = f"**Total: Done: {done_count} Ink Images: {ink_found_count}**"
        logger.info(f"Updated status title: Done={done_count}, Ink Area={ink_found_count}")
    
    def _show_help_modal(self, event=None):
        """Show help modal using JavaScript"""
        print("🔔 Help button clicked!", flush=True)
        logger.info("🔔 Help button clicked!")
        
        # Create HTML with JavaScript that shows a modal dialog
        # Add timestamp to force re-execution each time
        import time
        timestamp = int(time.time() * 1000)
        
        help_html = f'''
        <script id="help-script-{timestamp}">
        (function() {{
            // Remove existing modal if present
            const existing = document.getElementById('help-modal-overlay');
            if (existing) {{
                existing.remove();
            }}
            
            // Create modal HTML
            const modalHTML = `
                <div id="help-modal-overlay" style="
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0, 0, 0, 0.8);
                    z-index: 99999;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    font-family: Arial, sans-serif;
                ">
                    <div style="
                        background-color: white;
                        border-radius: 10px;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                        max-width: 700px;
                        max-height: 90vh;
                        overflow-y: auto;
                        position: relative;
                    ">
                        <div style="
                            background-color: #170f90;
                            color: white;
                            padding: 20px;
                            border-radius: 10px 10px 0 0;
                            position: sticky;
                            top: 0;
                            z-index: 1;
                        ">
                            <h2 style="margin: 0; font-size: 24px;">⌨️ Keyboard Shortcuts </h2>
                            <button onclick="document.getElementById('help-modal-overlay').remove()" style="
                                position: absolute;
                                top: 15px;
                                right: 15px;
                                background-color: #dc3545;
                                color: white;
                                border: none;
                                border-radius: 5px;
                                padding: 8px 15px;
                                cursor: pointer;
                                font-size: 16px;
                                font-weight: bold;
                            ">✕</button>
                        </div>
                        <div style="padding: 30px; line-height: 1.8;">
                            <h3 style="color: #170f90; margin-top: 0;">Navigation</h3>
                            <ul style="list-style: none; padding-left: 0;">
                                <li><strong>←</strong> [◀ Button] : Switch to previous image in dataset</li>
                                <li><strong>→</strong> [▶ Button] : Switch to next image in dataset</li>
                                <li><strong>Ctrl/Cmd + R</strong> [Reset View Button] : Reset zoom and center view</li>
                                <li><strong>V</strong> : Show/hide overview minimap</li>
                            </ul>
                            
                            <h3 style="color: #170f90;">Annotation and StatusControl</h3>
                            <ul style="list-style: none; padding-left: 0;">
                                <li><strong>Ctrl/Cmd + Z</strong> [⟲ UNDO Button] : Revert to previous annotation state</li>
                                <li><strong>Ctrl/Cmd + A</strong></strong> [⟳ REDO Button] : Restore undone annotation</li>
                                <li><strong>S</strong> [💾 SAVE Button] : Save current annotation and Mark image as complete and Ink found</li>
                                <!-- <li><strong>Ctrl/Cmd + ←</strong> [◀ Button] : Load previous saved annotation view</li> --> 
                                <!-- <li><strong>Ctrl/Cmd + →</strong> [▶ Button] : Load next saved annotation view</li> -->
                                <li><strong>D</strong> [Done Button] : Mark image as complete/incomplete</li>
                            </ul>
                            
                            <h3 style="color: #170f90;">Drawing Tools</h3>
                            <ul style="list-style: none; padding-left: 0;">
                                <li><strong>Shift</strong> : Hold while dragging to draw annotations</li>
                                <li><strong>Click + Backspace</strong> : Remove selected annotation line</li>
                                <li><strong>Ctrl/Cmd + Alt + Backspace</strong> [🗑️ Clear All Button] : Clear all drawings</li>
                                <li><strong>1-5</strong> : Adjust drawing line width (1=thin, 5=thick)</li>
                                <li><strong>C</strong> : Change annotation line color</li>
                            </ul>
                            
                            <hr style="margin: 20px 0; border: none; border-top: 2px solid #ddd;">
                            <p style="text-align: center; color: #666;"><strong>Total Shortcuts: 16</strong></p>
                        </div>
                    </div>
                </div>
            `;
            
            // Add modal to body
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            
            console.log('Help modal displayed - timestamp: {timestamp}');
        }})();
        </script>
        '''
        
        self.help_trigger.object = help_html
        print("✓ Help modal triggered", flush=True)
        logger.info("✓ Help modal triggered")
    
    def _on_selection_change(self, event):
        """Handle image selection change"""
        print("=" * 80, flush=True)
        print(f"🔄 SELECTION CHANGE TRIGGERED", flush=True)
        print(f"Old value: {event.old}", flush=True)
        print(f"New value: {event.new}", flush=True)
        print("=" * 80, flush=True)

        # Update current index based on selection
        for idx, img in enumerate(self.available_images):
            if img['svs_path'] == event.new:
                self.current_image_index = idx
                break
        
        # Update button states
        self._update_navigation_buttons()

        # Load new image
        print("Step 1: Loading new image...", flush=True)
        logger.info("Step 1: Loading new image...")
        self._load_image(event.new)
        filename = os.path.basename(event.new)
        cache.set(cache_key, filename)

        # Update image name display
        current_image_name = os.path.basename(event.new).replace('.svs', '')
        self.image_total_num_display.object = f"Total: {len(self.available_images)}"


        # Smart truncation for display
        max_display_length = 60
        if len(current_image_name) > max_display_length:
            display_name = current_image_name[:30] + '...' + current_image_name[-25:]
        else:
            display_name = current_image_name
        
        self.image_name_display.object = f"**Image:** {display_name}"

        print("Image Reloaed")
        if pn.state.location:
            pn.state.location.reload = True

        print(f"  ✓ New tool created for: {os.path.basename(event.new)}", flush=True)
        print(f"  ✓ New tool dimensions: {self.current_tool.dimensions}", flush=True)

        
        # Create completely new dashboard
        logger.info("Step 2: Creating new dashboard...")
        new_dashboard = self.current_tool.create_dashboard()
        logger.info(f"  ✓ Dashboard created")
        print(f"  - Dashboard has {len(new_dashboard.main)} main items", flush=True)
        logger.info(f"  - Dashboard has {len(new_dashboard.sidebar)} sidebar items")
        
        # Log sidebar contents
        print("Step 3: Inspecting new dashboard sidebar...", flush=True)
        logger.info("Step 3: Inspecting new dashboard sidebar...")
        for i, item in enumerate(new_dashboard.sidebar):
            item_type = type(item).__name__
            if hasattr(item, 'object'):
                content_preview = str(item.object)[:200]
            else:
                content_preview = str(item)[:200]
            print(f"  Sidebar[{i}]: {item_type}", flush=True)
            print(f"    Content: {content_preview}", flush=True)
            logger.info(f"  Sidebar[{i}]: {item_type}")
            logger.info(f"    Content: {content_preview}")
        
        # Update the main viewer - DON'T replace, just update parameters
        logger.info("Step 4: Updating viewer parameters in place...")
        new_viewer = new_dashboard.main[0] if new_dashboard.main else None
        
        if new_viewer:
            old_viewer = self.template.main[0] if self.template.main else None
            logger.info(f"  - Old viewer exists: {old_viewer is not None}")
            logger.info(f"  - New viewer exists: {new_viewer is not None}")
            
            if old_viewer and hasattr(old_viewer, 'dzi_url'):
                # Update all viewer parameters IN PLACE (don't replace the viewer)
                logger.info(f"  - Old dzi_url: {old_viewer.dzi_url}")
                logger.info(f"  - New dzi_url: {new_viewer.dzi_url}")
                
                # Only reload if DZI URL actually changed
                dzi_changed = old_viewer.dzi_url != new_viewer.dzi_url
                
                if dzi_changed:
                    print(f"🔄 Updating viewer from {old_viewer.dzi_url} to {new_viewer.dzi_url}", flush=True)
                else:
                    print(f"ℹ️  DZI URL unchanged: {old_viewer.dzi_url}", flush=True)
                    logger.info(f"  ℹ️  DZI URL unchanged, skipping reload")
                
                old_viewer.dzi_url = new_viewer.dzi_url
                old_viewer.width_px = new_viewer.width_px
                old_viewer.height_px = new_viewer.height_px
                old_viewer.max_zoom = new_viewer.max_zoom
                old_viewer.start_level = new_viewer.start_level
                old_viewer.center_offset_y = new_viewer.center_offset_y
                old_viewer.level_dimensions = new_viewer.level_dimensions
                
                # Note: dzi_url watch will automatically trigger map reload when DZI changes
                if dzi_changed:
                    print(f"  ✓ DZI URL updated, map will reload automatically", flush=True)
                    logger.info(f"  ✓ DZI URL updated, map will reload via dzi_url watch")
                else:
                    print(f"  ℹ️  DZI URL unchanged, no reload needed", flush=True)
                    logger.info(f"  ℹ️  DZI URL unchanged, no reload needed")

                # No sidebar to update - sidebar is hidden
                logger.info("Step 5: Skipping sidebar update (sidebar is hidden)")
                print(f"  ℹ️  Sidebar hidden, no update needed", flush=True)
                logger.info("  ℹ️ Main viewer kept (not replaced) - parameters updated in place")
            
                logger.info("=" * 80)
                logger.info(f"✅ SUCCESSFULLY SWITCHED TO: {os.path.basename(event.new)}")
                logger.info("=" * 80)
                print(f"✅ SUCCESSFULLY SWITCHED TO: {os.path.basename(event.new)}", flush=True)
    
    def get_template(self):
        """Get the template with selector"""
        return self.template
    



def get_token_from_url():
    """Extract token from URL parameters"""
    try:
        # Get token from URL query parameters
        if hasattr(pn.state, 'location') and pn.state.location:
            query_params = pn.state.location.search[1:] if pn.state.location.search else ""
            if query_params:
                from urllib.parse import parse_qs
                params = parse_qs(query_params)
                token = params.get('token', [None])[0]
                logger.info(f"Token extracted from URL: {'present' if token else 'missing'}")
                return token
    except Exception as e:
        logger.error(f"Error extracting token from URL: {e}")
    return None


def create_auth_error_page():
    """Create error page for invalid/missing token"""
    error_template = pn.template.BootstrapTemplate(
        title="Access Denied - Ink Annotation Tool"
    )
    
    error_content = pn.Column(
        pn.pane.Markdown(
            """
            # 🔒 Access Denied
            
            ## Invalid or missing authentication token
            
            Please use the correct URL with your authentication token:
            
            ```
            http://localhost:10333/annotation_tool?token=YOUR_TOKEN_HERE
            ```
            
            ### Troubleshooting:
            - Make sure you copied the entire URL including the token parameter
            - Check that your token hasn't expired (default timeout: 1 hour)
            - Contact your administrator if you don't have a valid token
            
            ---
            
            **Note:** Tokens are case-sensitive and must be used exactly as provided.
            """,
            sizing_mode='stretch_width'
        ),
        sizing_mode='stretch_width',
        styles={'padding': '20px'}
    )
    
    error_template.main.append(error_content)
    return error_template


def create_authenticated_app():
    """Create application with token authentication"""
    
    # Check if authentication is enabled
    if auth_manager.enabled:
        logger.info("🔐 Token authentication is ENABLED")
        
        token = get_token_from_url()
        
        if not token:
            logger.warning("❌ No token provided in URL")
            return create_auth_error_page()
        
        # Validate token
        user_id = auth_manager.validate_token(token)
        
        if not user_id:
            logger.warning(f"❌ Invalid token attempted: {token[:8]}...")
            return create_auth_error_page()
        
        # Store token and user_id in session cache
        pn.state.cache['token'] = token
        pn.state.cache['user_id'] = user_id
        
        logger.info(f"✅ User '{user_id}' authenticated successfully")
        logger.info(f"📊 Session will expire in {auth_manager.session_timeout} seconds")
    else:
        logger.info("🔓 Token authentication is DISABLED (development mode)")
        pn.state.cache['user_id'] = 'anonymous'
        pn.state.cache['token'] = None
    
    # Create and return the main application
    try:
        app = InteractiveSVSApp()
        return app.get_template()
    except Exception as e:
        logger.error(f"Failed to initialize app: {e}", exc_info=True)
        error_pane = pn.pane.Markdown(f"""
        # Error Loading Application
        
        **Error:** {str(e)}
        
        Please check:
        - DZI files exist in `/data/dzi_output/`
        - SVS files are in `/data/`
        - Files are not corrupted
        
        Run conversion: `docker exec ink_annotation_tool python /app/convert_to_dzi.py`
        """)
        return error_pane


# Initialize application
logger.info("=" * 80)
logger.info("Starting SVS Viewer with Image Selection")
logger.info("=" * 80)

try:
    template = create_authenticated_app()
    logger.info("Application initialized successfully")
    template.servable()
    
except Exception as e:
    logger.error(f"Failed to initialize: {e}", exc_info=True)
    error_pane = pn.pane.Markdown(f"""
    # Critical Error
    
    **Error:** {str(e)}
    
    Please contact system administrator.
    """)
    error_pane.servable()