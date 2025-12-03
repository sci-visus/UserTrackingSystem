"""
Utility functions for SVS annotation tool.

This module contains all utility functions for:
- Metadata loading (DZI, scalebar, SVS)
- Annotation file I/O operations
- Image discovery and loading
- Status management
"""

import os
import json
import glob
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


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


def load_scalebar_metadata(image_name, metadata_base_path):
    """Load scalebar metadata (mpp_x) for an image from svs_metadata directory"""


    metadata_path = os.path.join(metadata_base_path, f"{image_name}_svs_scalebar_metadata.json")
    
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
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/BRACS/', '/data/dzi_datasets/BRACS/')
        elif '/TCGA-BRCA/' in tiles_dir:
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/TCGA-BRCA/', '/data/dzi_datasets/TCGA/')
        elif '/BACH/' in tiles_dir:
            container_tiles_dir = tiles_dir.replace('/local/data/magicscan/dzi_ink_datasets/HnE/BACH/', '/data/dzi_datasets/BACH/')
        else:
            container_tiles_dir = tiles_dir
        
        # tiles_directory is the _files folder, parent has .dzi file
        dzi_parent = os.path.dirname(container_tiles_dir)
        #print(f"0008_DZI parent directory: {dzi_parent}") # Debugging line
        dzi_file = os.path.join(dzi_parent, base_name + '.dzi')
        #print(f"0009_DZI file path: {dzi_file}") # Debugging line
        
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
                'display_name': f"[{entry_num}] {base_name[:50]}..." if len(base_name) > 50 else f"[{entry_num}] {base_name}",
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
