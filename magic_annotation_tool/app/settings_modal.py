"""
Settings Modal UI for Keyboard Shortcuts
Panel-based interface for customizing keyboard shortcuts
"""
import panel as pn
import logging
from keyboard_shortcuts import CATEGORIES, DEFAULT_SHORTCUTS

logger = logging.getLogger(__name__)


def create_settings_modal(shortcut_manager, on_save_callback=None):
    """
    Create a settings modal for keyboard shortcuts
    
    Args:
        shortcut_manager: KeyboardShortcutManager instance
        on_save_callback: Optional callback function to call after save
    
    Returns:
        Panel modal component
    """
    
    # Store references to input widgets
    input_widgets = {}
    
    # Create category tabs
    category_tabs = []
    
    shortcuts_by_category = shortcut_manager.get_shortcuts_by_category()
    
    for category_id, shortcuts_list in shortcuts_by_category.items():
        category_info = CATEGORIES.get(category_id, {
            'name': category_id.replace('_', ' ').title(),
            'description': ''
        })
        
        category_widgets = []
        
        # Category description
        if category_info.get('description'):
            category_widgets.append(
                pn.pane.Markdown(
                    f"*{category_info['description']}*",
                    margin=(0, 0, 10, 0)
                )
            )
        
        # Create widgets for each shortcut in this category
        for shortcut in shortcuts_list:
            action = shortcut['action']
            keys = shortcut['keys']
            description = shortcut['description']
            
            # Action name header
            action_header = pn.pane.Markdown(
                f"**{action.replace('_', ' ').title()}**",
                margin=(15, 0, 5, 0)
            )
            
            # Description
            desc_pane = pn.pane.Markdown(
                f"*{description}*",
                margin=(0, 0, 5, 0),
                styles={'font-size': '0.9em', 'color': '#666'}
            )
            
            # Key input fields (support up to 3 key combinations)
            key_inputs = []
            for i in range(3):
                default_value = keys[i] if i < len(keys) else ""
                
                key_input = pn.widgets.TextInput(
                    name=f"Key {i+1}" if i > 0 else "Primary Key",
                    value=default_value,
                    placeholder="e.g., Ctrl+S, Cmd+S, Alt+ArrowLeft",
                    width=250
                )
                key_inputs.append(key_input)
                
                # Store reference
                input_widgets[f"{action}_{i}"] = key_input
            
            # Reset button for this action
            def create_reset_callback(action_name):
                def reset_action(event):
                    if action_name in DEFAULT_SHORTCUTS:
                        default_keys = DEFAULT_SHORTCUTS[action_name]['keys']
                        for i in range(3):
                            input_widgets[f"{action_name}_{i}"].value = (
                                default_keys[i] if i < len(default_keys) else ""
                            )
                        logger.info(f"Reset {action_name} to defaults")
                return reset_action
            
            reset_btn = pn.widgets.Button(
                name="Reset to Default",
                button_type="light",
                width=120,
                height=31,
                margin=(5, 0, 0, 0)
            )
            reset_btn.on_click(create_reset_callback(action))
            
            # Layout for this shortcut
            keys_row = pn.Row(*key_inputs, reset_btn, margin=(0, 0, 10, 0))
            
            category_widgets.extend([
                action_header,
                desc_pane,
                keys_row,
                pn.layout.Divider(margin=(5, 0, 5, 0))
            ])
        
        # Create scrollable column for this category
        category_column = pn.Column(
            *category_widgets,
            scroll=True,
            height=400,
            styles={'padding': '10px'}
        )
        
        category_tabs.append((category_info['name'], category_column))
    
    # Create tabs
    tabs = pn.Tabs(*category_tabs, dynamic=False)
    
    # Conflict warning area
    conflict_pane = pn.pane.Alert(
        "",
        alert_type="warning",
        visible=False,
        margin=(10, 0, 10, 0)
    )
    
    # Status message
    status_pane = pn.pane.Alert(
        "",
        alert_type="info",
        visible=False,
        margin=(10, 0, 10, 0)
    )
    
    def check_conflicts():
        """Check for conflicts in current input values"""
        # Build shortcuts dict from inputs
        temp_shortcuts = {}
        for action_name, config in shortcut_manager.shortcuts.items():
            keys = []
            for i in range(3):
                key = input_widgets.get(f"{action_name}_{i}", None)
                if key and key.value.strip():
                    keys.append(key.value.strip())
            
            temp_shortcuts[action_name] = {
                'keys': keys,
                'category': config['category'],
                'description': config['description'],
                'action': config['action']
            }
        
        # Find conflicts
        conflicts = shortcut_manager.find_conflicts(temp_shortcuts)
        
        if conflicts:
            conflict_text = "⚠️ **Conflicts detected:**\n\n"
            for conflict in conflicts:
                key = conflict['key']
                actions = [a.replace('_', ' ').title() for a in conflict['actions']]
                conflict_text += f"- `{key}` is used by: {', '.join(actions)}\n"
            
            conflict_pane.object = conflict_text
            conflict_pane.visible = True
            return False
        else:
            conflict_pane.visible = False
            return True
    
    def save_shortcuts(event):
        """Save current shortcuts"""
        # Check for conflicts
        if not check_conflicts():
            status_pane.object = "❌ Cannot save: Please resolve conflicts first"
            status_pane.alert_type = "danger"
            status_pane.visible = True
            return
        
        # Build shortcuts dict from inputs
        updated_shortcuts = {}
        for action_name, config in shortcut_manager.shortcuts.items():
            keys = []
            for i in range(3):
                key = input_widgets.get(f"{action_name}_{i}", None)
                if key and key.value.strip():
                    # Validate key combination
                    valid, msg = shortcut_manager.validate_key_combination(key.value.strip())
                    if not valid:
                        status_pane.object = f"❌ Invalid key '{key.value}' for {action_name}: {msg}"
                        status_pane.alert_type = "danger"
                        status_pane.visible = True
                        return
                    keys.append(key.value.strip())
            
            updated_shortcuts[action_name] = {
                'keys': keys,
                'category': config['category'],
                'description': config['description'],
                'action': config['action']
            }
        
        # Save
        success = shortcut_manager.save_shortcuts(updated_shortcuts)
        
        if success:
            status_pane.object = "✓ Shortcuts saved successfully! Refresh the page to apply changes."
            status_pane.alert_type = "success"
            status_pane.visible = True
            
            # Call callback if provided
            if on_save_callback:
                on_save_callback()
            
            logger.info("Keyboard shortcuts saved successfully")
        else:
            status_pane.object = "❌ Error saving shortcuts"
            status_pane.alert_type = "danger"
            status_pane.visible = True
    
    def reset_all(event):
        """Reset all shortcuts to defaults"""
        for action_name, config in DEFAULT_SHORTCUTS.items():
            default_keys = config['keys']
            for i in range(3):
                widget = input_widgets.get(f"{action_name}_{i}", None)
                if widget:
                    widget.value = default_keys[i] if i < len(default_keys) else ""
        
        status_pane.object = "All shortcuts reset to defaults (not saved yet)"
        status_pane.alert_type = "info"
        status_pane.visible = True
        logger.info("Reset all shortcuts to defaults")
    
    def check_conflicts_live(event):
        """Live conflict checking as user types"""
        check_conflicts()
    
    # Add live conflict checking to all inputs
    for widget in input_widgets.values():
        widget.param.watch(check_conflicts_live, 'value')
    
    # Buttons
    save_btn = pn.widgets.Button(
        name="💾 Save Changes",
        button_type="primary",
        width=150
    )
    save_btn.on_click(save_shortcuts)
    
    reset_all_btn = pn.widgets.Button(
        name="↺ Reset All to Default",
        button_type="warning",
        width=150
    )
    reset_all_btn.on_click(reset_all)
    
    close_btn = pn.widgets.Button(
        name="✖ Close",
        button_type="light",
        width=100
    )
    
    # Button row
    button_row = pn.Row(
        reset_all_btn,
        pn.Spacer(width=10),
        close_btn,
        pn.Spacer(width=10),
        save_btn,
        margin=(10, 0, 0, 0)
    )
    
    # Main modal content
    modal_content = pn.Column(
        pn.pane.Markdown("## ⌨️ Keyboard Shortcuts Settings", margin=(0, 0, 10, 0)),
        pn.pane.Markdown(
            "Customize keyboard shortcuts for the annotation tool. "
            "Use format: `Ctrl+Key`, `Cmd+Key`, `Alt+Key`, etc. "
            "You can specify up to 3 alternative key combinations per action.",
            styles={'font-size': '0.9em', 'color': '#666'},
            margin=(0, 0, 15, 0)
        ),
        conflict_pane,
        status_pane,
        tabs,
        button_row,
        width=800,
        height=650,
        styles={'padding': '20px'}
    )
    
    # Wrap the modal content in a simple HTML div with an ID
    # This ensures it renders and JS can find it
    modal_wrapper_html = pn.pane.HTML(
        '<div id="settings-modal-wrapper-container" class="settings-modal-wrapper"></div>',
        sizing_mode='fixed',
        width=850,
        height=700
    )
    
    # Create a Column to hold the modal content
    modal_content_column = pn.Column(
        modal_content,
        sizing_mode='fixed',
        width=850,
        height=700
    )
    
    # Add backdrop with ID
    backdrop = pn.pane.HTML(
        """
        <div id="settings-backdrop" style="
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.6);
            z-index: 9998;
        "></div>
        """,
        sizing_mode='stretch_both'
    )
    
    # Add JavaScript to move Panel content into the placeholder divs
    modal_js = pn.pane.HTML(
        """
        <script>
            (function() {
                console.log('⚙️  Settings modal JS initializing...');
                
                // Move Panel-generated content into our placeholder
                setTimeout(function() {
                    const placeholder = document.getElementById('settings-modal-placeholder');
                    const backdrop = document.getElementById('settings-backdrop');
                    
                    console.log('🔍 Found placeholder:', !!placeholder, 'backdrop:', !!backdrop);
                    
                    if (placeholder) {
                        // Find all bk-Column elements (Panel generates these)
                        const columns = document.querySelectorAll('.bk-Column');
                        
                        // Look for the Column that contains our tabs (settings content)
                        for (let col of columns) {
                            const tabs = col.querySelector('.bk-Tabs');
                            if (tabs) {
                                console.log('✓ Found settings content, moving to placeholder');
                                // Move all children into placeholder
                                while (col.firstChild) {
                                    placeholder.appendChild(col.firstChild);
                                }
                                col.style.display = 'none';
                                break;
                            }
                        }
                    }
                }, 1000);
                
                window.showSettingsModal = function() {
                    console.log('showSettingsModal called');
                    const placeholder = document.getElementById('settings-modal-placeholder');
                    const backdrop = document.getElementById('settings-backdrop');
                    
                    if (placeholder && backdrop) {
                        placeholder.classList.add('show');
                        backdrop.classList.add('show');
                        console.log('✓ Modal shown');
                    } else {
                        console.error('❌ Not found - placeholder:', !!placeholder, 'backdrop:', !!backdrop);
                    }
                };
                
                window.hideSettingsModal = function() {
                    console.log('hideSettingsModal called');
                    const placeholder = document.getElementById('settings-modal-placeholder');
                    const backdrop = document.getElementById('settings-backdrop');
                    
                    if (placeholder && backdrop) {
                        placeholder.classList.remove('show');
                        backdrop.classList.remove('show');
                        console.log('✓ Modal hidden');
                    }
                };
                
                // Close on backdrop click
                document.addEventListener('click', function(e) {
                    if (e.target.id === 'settings-backdrop' && e.target.classList.contains('show')) {
                        window.hideSettingsModal();
                    }
                });
                
                console.log('✓ Modal JS ready');
            })();
        </script>
        """,
        sizing_mode='stretch_both'
    )
    
    # Combine all elements - backdrop, wrapper, content, JS
    full_modal_wrapper = pn.Column(
        backdrop,
        modal_wrapper_html,
        modal_content_column,
        modal_js,
        sizing_mode='stretch_both'
    )
    
    # Close button handler - call JS function
    def close_modal(event):
        logger.info("Closing modal via close button")
        print("DEBUG: Close button clicked, hiding modal", flush=True)
        status_pane.visible = False
        # Trigger JS to hide modal by injecting a script
        modal_js.object = modal_js.object.replace('</script>', '') + """
            if (window.hideSettingsModal) window.hideSettingsModal();
        </script>
        """
    
    close_btn.on_click(close_modal)
    
    # Store references for external access
    full_modal_wrapper._backdrop = backdrop
    full_modal_wrapper._modal = modal_wrapper_html
    full_modal_wrapper._modal_content = modal_content_column
    full_modal_wrapper._modal_js = modal_js
    
    return full_modal_wrapper, close_btn


def create_settings_button_and_modal(shortcut_manager, on_save_callback=None):
    """
    Create both the settings button and modal together
    
    Returns:
        (button, modal) tuple
    """
    print("========== create_settings_button_and_modal() START ==========", flush=True)
    print(f"DEBUG settings_modal: Received shortcut_manager: {shortcut_manager}", flush=True)
    print(f"DEBUG settings_modal: Received on_save_callback: {on_save_callback}", flush=True)
    
    # Create modal first (hidden by default)
    print("DEBUG settings_modal: About to create modal", flush=True)
    modal, close_btn = create_settings_modal(shortcut_manager, on_save_callback)
    modal.visible = False
    print(f"DEBUG settings_modal: Modal created with visible={modal.visible}", flush=True)
    
    # Store visibility state
    modal_state = {'visible': False}
    
    # Define toggle function - use JavaScript to show/hide
    def toggle_modal(event):
        print("========== SETTINGS BUTTON CLICKED! ==========", flush=True)
        print(f"DEBUG toggle_modal: Event received: {event}", flush=True)
        logger.info(f"⚙️  Settings button clicked! Event: {event}")
        try:
            # Toggle state
            modal_state['visible'] = not modal_state['visible']
            print(f"DEBUG toggle_modal: Toggling to visible={modal_state['visible']}", flush=True)
            
            # Call JS function via script injection
            if modal_state['visible']:
                print("DEBUG toggle_modal: Calling showSettingsModal", flush=True)
                modal._modal_js.object = modal._modal_js.object + """
                <script>
                    if (window.showSettingsModal) {
                        window.showSettingsModal();
                    } else {
                        console.error('window.showSettingsModal not ready');
                    }
                </script>
                """
            else:
                print("DEBUG toggle_modal: Calling hideSettingsModal", flush=True)
                modal._modal_js.object = modal._modal_js.object + """
                <script>
                    if (window.hideSettingsModal) {
                        window.hideSettingsModal();
                    } else {
                        console.error('window.hideSettingsModal not ready');
                    }
                </script>
                """
            
            logger.info(f"✓ Modal toggle complete, visible={modal_state['visible']}")
            print("========== SETTINGS BUTTON CLICK COMPLETE ==========", flush=True)
        except Exception as e:
            print(f"DEBUG toggle_modal: EXCEPTION: {e}", flush=True)
            import traceback
            traceback.print_exc()
            logger.error(f"❌ Error toggling modal: {e}", exc_info=True)
    
    # Create settings button with proper alignment and onclick handler
    settings_btn = pn.widgets.Button(
        name="⚙️",
        button_type="light",
        width=40,
        height=35,
        margin=(10, 10),
        stylesheets=["""
        :host(.solid) .bk-btn {
            background-color: #f8f9fa !important;
            color: #212529 !important;
            border: 2px solid #ffffff !important;
            font-weight: bold !important;
            font-size: 18px !important;
            box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
            padding: 6px 10px;
            margin-top: 54px;
            position: relative;
        }
        :host(.solid) .bk-btn:hover {
            background-color: #e2e6ea !important;
            box-shadow: 0 3px 7px rgba(0,0,0,0.5) !important;
        }
        :host(.solid) .bk-btn::after {
            content: 'Settings';
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
    print(f"DEBUG settings_modal: Button created: {settings_btn}", flush=True)
    print(f"DEBUG settings_modal: Button name: {settings_btn.name}", flush=True)
    print(f"DEBUG settings_modal: Button type: {type(settings_btn)}", flush=True)
    
    # Register click handler using on_click (simpler and more reliable)
    print("DEBUG settings_modal: About to register on_click handler", flush=True)
    settings_btn.on_click(toggle_modal)
    print("DEBUG settings_modal: on_click handler registered successfully", flush=True)
    logger.info("⚙️  Settings button click handler registered with on_click")
    
    # Also close modal when close button is clicked
    def close_modal_handler(event):
        print("DEBUG: Close button clicked in modal", flush=True)
        logger.info("Close button clicked in modal")
        modal.visible = False
    
    close_btn.param.watch(close_modal_handler, 'clicks')
    
    logger.info(f"✓ Settings button created: name='{settings_btn.name}', button_type='{settings_btn.button_type}'")
    logger.info(f"✓ Modal created: visible={modal.visible}, has {len(modal.objects)} objects")
    logger.info("✓ Click handlers registered for both settings and close buttons")
    
    print(f"DEBUG settings_modal: Returning button={settings_btn}, modal={modal}", flush=True)
    print("========== create_settings_button_and_modal() END ==========", flush=True)
    return settings_btn, modal
