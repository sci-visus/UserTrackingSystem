"""
Main application entry point for Magic Annotation Tool.

This module contains:
- Panel extension initialization
- InteractiveSVSApp class (main controller)
- Authentication functions
- Application servable setup
"""

import panel as pn
import param
import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Import modules
from utility import *
from annotation import SVSAnnotationTool
from redis_cache import cache
from keyboard_shortcuts import KeyboardShortcutManager
from settings_modal import create_settings_button_and_modal
from auth_middleware import auth_manager
from redis_helper import redis_helper

cache_key = "annotation_tool_cache_v1"
session_key_prefix = "active_session:" 

# Load environment variables from .env file
load_dotenv()

# Set up logging with unbuffered output
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Force flush for all log handlers
for handler in logging.root.handlers:
    handler.setLevel(logging.INFO)
    handler.flush = lambda: sys.stdout.flush()


# Initialize Panel extension - load JS/CSS globally
# to include Leaflet’s CSS and JS globally so we can use Leaflet maps inside a Panel dashboard.

pn.extension(sizing_mode="stretch_width", 
             css_files=[
                 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.css'
             ], 
             js_files={
                 'leaflet': 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.js'
             })


###############################################################

# Create interactive application with image selector
class InteractiveSVSApp:
    """Interactive SVS viewer with image selection"""
    
    def __init__(self):
        logger.info("=" * 80)
        logger.info("0004_InteractiveSVSApp.__init__() starting")
        logger.info("=" * 80)

        # Initialize keyboard shortcuts manager
        self.shortcut_manager = KeyboardShortcutManager()
        logger.info("0005_Keyboard shortcuts manager initialized")


        logger.info("0006_About to call get_available_images")
        self.available_images = get_available_images()
        self.current_tool = None
        self.current_image_index = 0  # Track current image index
        
        logger.info(f"0007_Found {len(self.available_images)} available images")
        
        # Create image selector
        print("0008_Creating image_options dictionary", flush=True)
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
                logger.info(f"0003_Token extracted from URL: {'present' if token else 'missing'}")
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
            http://localhost:10333/app?token=YOUR_TOKEN_HERE
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
        logger.info("0002_Token authentication is ENABLED")
        
        token = get_token_from_url()
        
        if not token:
            logger.warning("❌ No token provided in URL")
            return create_auth_error_page()
        
        # Validate token
        user_id = auth_manager.validate_token(token)
        
        if not user_id:
            logger.warning(f"❌ Invalid token attempted: {token[:8]}...")
            return create_auth_error_page()
        
        # Generate unique session ID for this browser tab
        import uuid
        session_id = str(uuid.uuid4())
        
        # Store token and user_id in session cache
        pn.state.cache['token'] = token
        pn.state.cache['user_id'] = user_id
        pn.state.cache['session_id'] = session_id
        
        # Track this session in Redis with 5-minute TTL (will auto-expire)
        session_data = {
            'user_id': user_id,
            'token': token[:8] + '...',  # Store partial token for privacy
            'started_at': str(datetime.now()),
            'tab_id': session_id[:8]  # Short ID for display
        }
        cache.set(f"{session_key_prefix}{session_id}", session_data, ttl=300)  # 5 minutes
        
        # Count active sessions
        active_sessions = cache.keys(f"{session_key_prefix}*")
        session_count = len(active_sessions)
        
        logger.info(f"✅ User '{user_id}' authenticated successfully")
        logger.info(f"🌐 Session ID: {session_id[:8]}...")
        logger.info(f"📊 Active sessions for all users: {session_count}")
        logger.info(f"⏰ Session will auto-expire in 300 seconds without heartbeat")
        
        # Add periodic heartbeat to keep session alive
        def send_heartbeat():
            """Refresh session TTL every 2 minutes while tab is open"""
            import time
            import threading
            while True:
                time.sleep(120)  # 2 minutes
                try:
                    # Check if this session is still active in Panel
                    if hasattr(pn.state, 'curdoc') and pn.state.curdoc:
                        # Refresh session in Redis
                        session_data['last_heartbeat'] = str(datetime.now())
                        cache.set(f"{session_key_prefix}{session_id}", session_data, ttl=300)
                        
                        # Count remaining sessions
                        remaining = len(cache.keys(f"{session_key_prefix}*"))
                        logger.info(f"💓 Heartbeat: Session {session_id[:8]} alive (total: {remaining})")
                    else:
                        logger.info(f"🔚 Session {session_id[:8]} ended (Panel closed)")
                        break
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")
                    break
        
        # Start heartbeat in background thread
        import threading
        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True, name=f"heartbeat-{session_id[:8]}")
        heartbeat_thread.start()
        logger.info(f"✓ Heartbeat started for session {session_id[:8]}")
        
        # Register cleanup (may or may not fire, but try anyway)
        def cleanup_session(session_context):
            try:
                cache.delete(f"{session_key_prefix}{session_id}")
                remaining = len(cache.keys(f"{session_key_prefix}*"))
                logger.info(f"🔚 Session {session_id[:8]} closed gracefully. Remaining: {remaining}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
        
        pn.state.on_session_destroyed(cleanup_session)
        
    else:
        logger.info("🔓 Token authentication is DISABLED (development mode)")
        pn.state.cache['user_id'] = 'anonymous'
        pn.state.cache['token'] = None
        pn.state.cache['session_id'] = 'dev-session'
    
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
logger.info("0001_Starting SVS Viewer with Image Selection")
logger.info("=" * 80)

# Start background session monitor
def monitor_sessions():
    """Log active sessions every 60 seconds"""
    import time
    import threading
    while True:
        time.sleep(60)  # Check every minute
        try:
            active_sessions = cache.keys(f"{session_key_prefix}*")
            session_count = len(active_sessions)
            #logger.info(f"📊 Active sessions: {session_count}")
            
            # Log details of each session
            for session_key in active_sessions:
                try:
                    session_key_str = session_key.decode('utf-8') if isinstance(session_key, bytes) else session_key
                    session_id_only = session_key_str.replace(session_key_prefix, "")
                    data = cache.get(session_id_only)
                    if data:
                        data_dict = json.loads(data) if isinstance(data, str) else data
                        logger.info(f"  - {data_dict.get('tab_id', 'unknown')}: User {data_dict.get('user_id', 'unknown')}")
                except Exception as e:
                    logger.error(f"Error reading session: {e}")
        except Exception as e:
            logger.error(f"Session monitor error: {e}")

import threading
monitor_thread = threading.Thread(target=monitor_sessions, daemon=True, name="session-monitor")
monitor_thread.start()
logger.info("✓ Session monitor started (logs every 60s)")

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