# Customizable Keyboard Shortcuts

This feature allows users to customize all keyboard shortcuts in the Magic Annotation Tool through a user-friendly settings interface.

## Features

### 1. **Settings Button**
- Located in the top-right corner of the header (⚙️ icon)
- Click to open the keyboard shortcuts customization modal
- Visible at all times for easy access

### 2. **Customization Interface**
- **Organized by Category**: Shortcuts are grouped into logical categories:
  - **Navigation**: Move between views and images
  - **Annotation Control**: Undo, redo, and save operations
  - **Status Marking**: Mark image status (done, ink found)
  - **View Control**: Control viewer display options

- **Multiple Key Combinations**: Each action supports up to 3 alternative key combinations
  - Primary key (always shown)
  - Secondary key (optional)
  - Tertiary key (optional)

### 3. **Conflict Detection**
- Real-time validation as you type
- Warns if the same key combination is assigned to multiple actions
- Visual feedback with warning messages

### 4. **Key Validation**
- Ensures valid key format (e.g., `Ctrl+S`, `Alt+ArrowLeft`)
- Supports common modifiers: `Ctrl`, `Cmd`, `Alt`, `Shift`
- Supports all standard keys including arrow keys

### 5. **Persistence**
- Settings are saved to `/data/keyboard_shortcuts.json`
- Persists across application restarts
- Shared across all users (can be modified for per-user settings)

## Default Shortcuts

### Navigation
- **Previous View**: `Ctrl+ArrowLeft` / `Cmd+ArrowLeft`
- **Next View**: `Ctrl+ArrowRight` / `Cmd+ArrowRight`
- **Recenter**: `Ctrl+R` / `Cmd+R`
- **Previous Image**: `Alt+ArrowLeft`
- **Next Image**: `Alt+ArrowRight`

### Annotation Control
- **Undo**: `Ctrl+Z` / `Cmd+Z`
- **Redo**: `Ctrl+Y` / `Cmd+Shift+Z`
- **Save**: `Ctrl+S` / `Cmd+S`

### Status Marking
- **Mark Done**: `Ctrl+D` / `Cmd+D`
- **Toggle Ink Found**: `Ctrl+I` / `Cmd+I`

### View Control
- **Toggle Minimap**: `Ctrl+H` / `Cmd+H`

## Usage

### Opening Settings
1. Click the ⚙️ button in the top-right corner of the header
2. The settings modal will open

### Customizing a Shortcut
1. Find the action you want to customize in the appropriate category tab
2. Click in the text field for the key combination
3. Type the new key combination (e.g., `Ctrl+Alt+S`)
4. The system will validate your input in real-time
5. If there are conflicts, they will be highlighted

### Saving Changes
1. Review your changes and resolve any conflicts
2. Click **"💾 Save Changes"** button
3. You'll see a success message
4. **Refresh the page** to apply the new shortcuts

### Resetting Shortcuts
- **Reset Individual**: Click "Reset to Default" next to any shortcut
- **Reset All**: Click "↺ Reset All to Default" button at the bottom

## Key Format

Shortcuts must follow this format: `Modifier+Key`

### Valid Modifiers
- `Ctrl` - Control key (Windows/Linux)
- `Cmd` - Command key (macOS)
- `Alt` - Alt/Option key
- `Shift` - Shift key
- `Meta` - Meta key (same as Cmd)

### Valid Keys
- Letters: `a`, `b`, `c`, ... `z`
- Numbers: `0`, `1`, `2`, ... `9`
- Arrow keys: `ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`
- Function keys: `F1`, `F2`, ... `F12`
- Special keys: `Enter`, `Escape`, `Space`, `Tab`

### Examples
- ✓ `Ctrl+S` - Valid
- ✓ `Cmd+Alt+ArrowLeft` - Valid (multiple modifiers)
- ✓ `Shift+F5` - Valid
- ✗ `Ctrl+` - Invalid (no main key)
- ✗ `Ctrl` - Invalid (only modifier)
- ✗ `S` - Valid but not recommended (no modifier)

## Technical Details

### Architecture

```
┌─────────────────────────────────────┐
│  annotation_tool.py                 │
│  - InteractiveSVSApp                │
│  - Initializes KeyboardShortcutMgr  │
│  - Creates settings button/modal    │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  keyboard_shortcuts.py              │
│  - KeyboardShortcutManager          │
│  - Load/Save configuration          │
│  - Validation & conflict detection  │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  settings_modal.py                  │
│  - Panel-based UI                   │
│  - Category tabs                    │
│  - Real-time validation             │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  /data/keyboard_shortcuts.json      │
│  - Persistent storage               │
└─────────────────────────────────────┘
```

### JavaScript Integration

The shortcuts are dynamically loaded into JavaScript on page load:

```javascript
// Shortcuts are passed as JSON from Python
let shortcuts = JSON.parse(data.shortcuts_config);

// Dynamic event listener registration
document.addEventListener('keydown', function(e) {
    for (const [actionName, config] of Object.entries(shortcuts)) {
        for (const keyCombo of config.keys) {
            if (matchesKeyCombination(e, keyCombo)) {
                e.preventDefault();
                data.keyboard_trigger = config.action;
                return;
            }
        }
    }
});
```

### Files Modified

1. **`annotation_tool.py`**
   - Added imports for `KeyboardShortcutManager` and `create_settings_button_and_modal`
   - Initialize shortcut manager in `InteractiveSVSApp.__init__()`
   - Create settings button and modal
   - Add settings button to header
   - Pass shortcut manager to `SVSAnnotationTool`
   - Updated JavaScript keyboard handler to use dynamic shortcuts

2. **`keyboard_shortcuts.py`** (new)
   - `KeyboardShortcutManager` class
   - Default shortcuts configuration
   - Category definitions
   - Validation and conflict detection
   - Save/load functionality

3. **`settings_modal.py`** (new)
   - Panel-based UI components
   - Category tabs
   - Input widgets with validation
   - Save/reset functionality

### Configuration File

Location: `/data/keyboard_shortcuts.json`

Format:
```json
{
  "undo": {
    "keys": ["Ctrl+Z", "Cmd+Z"],
    "description": "Revert to previous annotation state",
    "category": "annotation_control",
    "action": "undo"
  },
  "save": {
    "keys": ["Ctrl+S", "Cmd+S"],
    "description": "Save current annotation as new view",
    "category": "annotation_control",
    "action": "save"
  }
  // ... more shortcuts
}
```

## Troubleshooting

### Shortcuts not working after save
**Solution**: Refresh the page (F5 or Ctrl+R) to reload the JavaScript with new shortcuts.

### Conflict warnings
**Solution**: Change one of the conflicting shortcuts to use a different key combination.

### Invalid key combination error
**Solution**: Ensure your shortcut follows the format `Modifier+Key` (e.g., `Ctrl+S`, not just `S`).

### Settings not persisting
**Solution**: Check that `/data` directory has write permissions. The file `/data/keyboard_shortcuts.json` should be created with `rw-rw-rw-` permissions.

### Can't access settings modal
**Solution**: Check browser console for JavaScript errors. Ensure Panel version is compatible.

## Future Enhancements

Possible improvements for future versions:

1. **Per-user settings**: Store shortcuts per user in database
2. **Import/Export**: Share shortcut configurations between users
3. **Keyboard recording**: Click a button and press keys to record combination
4. **Visual shortcuts guide**: Show current shortcuts in help modal
5. **Action search**: Filter shortcuts by action name
6. **Preset templates**: Quick-load different shortcut schemes (Vim-like, Emacs-like, etc.)
7. **Conflict resolution wizard**: Guided process to resolve conflicts
8. **Undo history**: Revert to previous shortcut configurations

## Testing

Run the test script to verify functionality:

```bash
cd /local/data/magicscan/dev_sam/ink_annotation_tool/app
python test_shortcuts.py
```

This will test:
- Manager initialization
- Default shortcuts loading
- Categorization
- Conflict detection
- Key validation
- Save/load functionality
- Reset functionality

## Support

For issues or questions:
1. Check the browser console for JavaScript errors
2. Check application logs for Python errors
3. Verify `/data/keyboard_shortcuts.json` permissions
4. Try resetting to defaults

---

**Version**: 1.0  
**Last Updated**: November 24, 2025  
**Author**: Magic Annotation Tool Team
