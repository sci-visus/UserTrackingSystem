"""
Keyboard Shortcuts Manager
Handles loading, saving, validating, and generating JavaScript for customizable keyboard shortcuts
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# Default keyboard shortcuts configuration
DEFAULT_SHORTCUTS = {
    "undo": {
        "keys": ["Ctrl+Z", "Cmd+Z"],
        "description": "Revert to previous annotation state",
        "category": "annotation_control",
        "action": "undo"
    },
    "redo": {
        "keys": ["Ctrl+A", "Cmd+A"],
        "description": "Restore undone annotation",
        "category": "annotation_control",
        "action": "redo"
    },
    "save": {
        "keys": ["S"],
        "description": "Save current annotation as new view",
        "category": "annotation_control",
        "action": "save"
    },
    "prev": {
        "keys": ["Ctrl+ArrowLeft", "Cmd+ArrowLeft"],
        "description": "Load previous saved view",
        "category": "navigation",
        "action": "prev"
    },
    "next": {
        "keys": ["Ctrl+ArrowRight", "Cmd+ArrowRight"],
        "description": "Load next saved view",
        "category": "navigation",
        "action": "next"
    },
    "recenter": {
        "keys": ["Ctrl+R", "Cmd+R"],
        "description": "Reset view to center",
        "category": "navigation",
        "action": "recenter"
    },
    "prev_image": {
        "keys": ["ArrowLeft"],
        "description": "Load previous image",
        "category": "navigation",
        "action": "prev_image"
    },
    "next_image": {
        "keys": ["ArrowRight"],
        "description": "Load next image",
        "category": "navigation",
        "action": "next_image"
    },
    "toggle_minimap": {
        "keys": ["V"],
        "description": "Toggle minimap visibility",
        "category": "view_control",
        "action": "toggle_minimap"
    },
    "done": {
        "keys": ["D"],
        "description": "Mark image as done (no ink)",
        "category": "status_marking",
        "action": "done"
    }
    # ink_found shortcut removed - button is disabled and only updated by Done/Save buttons
}

CATEGORIES = {
    "navigation": {
        "name": "Navigation",
        "description": "Navigate between views and images",
        "order": 1
    },
    "annotation_control": {
        "name": "Annotation Control",
        "description": "Undo, redo, and save annotations",
        "order": 2
    },
    "status_marking": {
        "name": "Status Marking",
        "description": "Mark image status (done, ink found)",
        "order": 3
    },
    "view_control": {
        "name": "View Control",
        "description": "Control viewer display options",
        "order": 4
    }
}


class KeyboardShortcutManager:
    """Manages keyboard shortcuts configuration"""
    
    def __init__(self, config_file='/data/keyboard_shortcuts.json'):
        self.config_file = config_file
        self.shortcuts = self.load_shortcuts()
        logger.info(f"Initialized KeyboardShortcutManager with {len(self.shortcuts)} shortcuts")
    
    def load_shortcuts(self):
        """Load shortcuts from file or return defaults"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    custom_shortcuts = json.load(f)
                logger.info(f"✓ Loaded custom shortcuts from {self.config_file}")
                
                # Merge with defaults to ensure all shortcuts exist
                merged = DEFAULT_SHORTCUTS.copy()
                for key, value in custom_shortcuts.items():
                    if key in merged:
                        merged[key]['keys'] = value.get('keys', merged[key]['keys'])
                
                return merged
            except Exception as e:
                logger.error(f"Error loading shortcuts: {e}, using defaults")
                return DEFAULT_SHORTCUTS.copy()
        else:
            logger.info("No custom shortcuts file found, using defaults")
            return DEFAULT_SHORTCUTS.copy()
    
    def save_shortcuts(self, shortcuts):
        """Save shortcuts to file"""
        try:
            # Validate before saving
            conflicts = self.find_conflicts(shortcuts)
            if conflicts:
                logger.warning(f"Saving shortcuts with conflicts: {conflicts}")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                json.dump(shortcuts, f, indent=2)
            
            os.chmod(self.config_file, 0o666)  # rw-rw-rw-
            self.shortcuts = shortcuts
            logger.info(f"✓ Saved shortcuts to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving shortcuts: {e}")
            return False
    
    def reset_to_defaults(self):
        """Reset all shortcuts to default values"""
        self.shortcuts = DEFAULT_SHORTCUTS.copy()
        return self.save_shortcuts(self.shortcuts)
    
    def reset_shortcut(self, action_name):
        """Reset a single shortcut to default"""
        if action_name in DEFAULT_SHORTCUTS:
            self.shortcuts[action_name] = DEFAULT_SHORTCUTS[action_name].copy()
            return self.save_shortcuts(self.shortcuts)
        return False
    
    def find_conflicts(self, shortcuts=None):
        """Find conflicting key combinations"""
        if shortcuts is None:
            shortcuts = self.shortcuts
        
        conflicts = []
        key_map = {}  # key -> list of actions using this key
        
        for action_name, config in shortcuts.items():
            for key in config.get('keys', []):
                normalized_key = self.normalize_key(key)
                if normalized_key not in key_map:
                    key_map[normalized_key] = []
                key_map[normalized_key].append(action_name)
        
        # Find keys used by multiple actions
        for key, actions in key_map.items():
            if len(actions) > 1:
                conflicts.append({
                    'key': key,
                    'actions': actions
                })
        
        return conflicts
    
    def normalize_key(self, key_combination):
        """Normalize key combination for comparison (case-insensitive, ordered modifiers)"""
        parts = key_combination.split('+')
        
        # Normalize modifier keys
        modifiers = []
        main_key = None
        
        for part in parts:
            part_lower = part.lower()
            if part_lower in ['ctrl', 'cmd', 'alt', 'shift', 'meta']:
                modifiers.append(part_lower)
            else:
                main_key = part_lower
        
        # Sort modifiers for consistency
        modifiers.sort()
        
        if main_key:
            return '+'.join(modifiers + [main_key])
        return '+'.join(modifiers)
    
    def validate_key_combination(self, key_combination):
        """Validate a key combination string"""
        if not key_combination or not isinstance(key_combination, str):
            return False, "Key combination must be a non-empty string"
        
        parts = key_combination.split('+')
        if len(parts) < 1:
            return False, "Key combination must have at least one key"
        
        # Valid modifier keys
        valid_modifiers = {'ctrl', 'cmd', 'alt', 'shift', 'meta'}
        
        # Check each part
        has_main_key = False
        for part in parts:
            if not part:
                return False, "Empty key part in combination"
            
            part_lower = part.lower()
            if part_lower not in valid_modifiers:
                has_main_key = True
        
        if not has_main_key:
            return False, "Key combination must have a non-modifier key"
        
        return True, "Valid"
    
    def generate_js_handler(self):
        """Generate JavaScript keyboard event handler code"""
        js_conditions = []
        
        for action_name, config in self.shortcuts.items():
            action = config['action']
            keys = config.get('keys', [])
            
            for key_combo in keys:
                condition = self._generate_js_condition(key_combo, action)
                if condition:
                    js_conditions.append(condition)
        
        # Combine all conditions into one handler
        js_code = "document.addEventListener('keydown', function(e) {\n"
        
        for i, condition in enumerate(js_conditions):
            if i == 0:
                js_code += f"    if {condition}\n"
            else:
                js_code += f"    else if {condition}\n"
        
        js_code += "});\n"
        
        return js_code
    
    def _generate_js_condition(self, key_combo, action):
        """Generate JavaScript condition for a key combination"""
        parts = key_combo.split('+')
        
        conditions = []
        main_key = None
        
        has_ctrl = False
        has_cmd = False
        has_alt = False
        has_shift = False
        
        for part in parts:
            part_lower = part.lower()
            if part_lower == 'ctrl':
                has_ctrl = True
            elif part_lower == 'cmd' or part_lower == 'meta':
                has_cmd = True
            elif part_lower == 'alt':
                has_alt = True
            elif part_lower == 'shift':
                has_shift = True
            else:
                main_key = part
        
        # Build condition
        condition_parts = []
        
        if has_ctrl or has_cmd:
            condition_parts.append("(e.ctrlKey || e.metaKey)")
        else:
            condition_parts.append("!e.ctrlKey && !e.metaKey")
        
        if has_alt:
            condition_parts.append("e.altKey")
        else:
            condition_parts.append("!e.altKey")
        
        if has_shift:
            condition_parts.append("e.shiftKey")
        else:
            condition_parts.append("!e.shiftKey")
        
        # Handle main key
        if main_key:
            # Special cases for arrow keys
            key_name_map = {
                'ArrowLeft': 'ArrowLeft',
                'ArrowRight': 'ArrowRight',
                'ArrowUp': 'ArrowUp',
                'ArrowDown': 'ArrowDown'
            }
            
            if main_key in key_name_map:
                condition_parts.append(f"e.key === '{key_name_map[main_key]}'")
            else:
                condition_parts.append(f"e.key === '{main_key.lower()}'")
        
        full_condition = "(" + " && ".join(condition_parts) + ") {\n"
        full_condition += "        e.preventDefault();\n"
        full_condition += f"        console.log('⌨️  Keyboard: {action.title()} ({key_combo})');\n"
        full_condition += f"        data.keyboard_trigger = '{action}';\n"
        full_condition += "    }"
        
        return full_condition
    
    def get_shortcuts_by_category(self):
        """Get shortcuts organized by category"""
        by_category = {}
        
        for action_name, config in self.shortcuts.items():
            category = config.get('category', 'other')
            if category not in by_category:
                by_category[category] = []
            
            by_category[category].append({
                'action': action_name,
                'keys': config.get('keys', []),
                'description': config.get('description', ''),
                'category': category
            })
        
        # Sort categories by order
        sorted_categories = sorted(
            by_category.items(),
            key=lambda x: CATEGORIES.get(x[0], {}).get('order', 999)
        )
        
        return dict(sorted_categories)
    
    def export_shortcuts(self, filepath):
        """Export shortcuts to a file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.shortcuts, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error exporting shortcuts: {e}")
            return False
    
    def import_shortcuts(self, filepath):
        """Import shortcuts from a file"""
        try:
            with open(filepath, 'r') as f:
                imported = json.load(f)
            
            # Validate imported shortcuts
            for action_name, config in imported.items():
                if action_name not in DEFAULT_SHORTCUTS:
                    logger.warning(f"Unknown action '{action_name}' in imported shortcuts")
                    continue
                
                # Validate keys
                for key in config.get('keys', []):
                    valid, msg = self.validate_key_combination(key)
                    if not valid:
                        logger.warning(f"Invalid key '{key}' for action '{action_name}': {msg}")
            
            self.shortcuts = imported
            return self.save_shortcuts(self.shortcuts)
        except Exception as e:
            logger.error(f"Error importing shortcuts: {e}")
            return False
