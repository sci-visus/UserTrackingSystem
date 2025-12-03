
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
from utility import *
from leaflet_viewer import SVSLeafletViewer


# Get port configuration from environment variables
DZI_SERVER_PORT = os.getenv('DZI_SERVER_PORT', '10566')
cache_key = "annotation_tool_cache_v1"


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
        
        print(f"Loading metadata from: {metadata_path}")
        metadata = load_metadata(metadata_path)

        # Load scalebar metadata (mpp_x → mm_per_pixel)
        metadata_base_path = os.path.dirname(metadata_path)
        
        self.mm_per_pixel = load_scalebar_metadata(base_name, metadata_base_path)
        
        # Load SVS metadata for accurate magnification display
        svs_metadata_path = os.path.join(metadata_base_path, f"{base_name}_svs_scalebar_metadata.json")
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