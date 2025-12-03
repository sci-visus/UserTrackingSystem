"""
Quick test script for keyboard shortcuts functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from keyboard_shortcuts import KeyboardShortcutManager, DEFAULT_SHORTCUTS, CATEGORIES

def test_keyboard_shortcuts():
    print("=" * 80)
    print("Testing Keyboard Shortcuts Manager")
    print("=" * 80)
    
    # Initialize manager
    manager = KeyboardShortcutManager(config_file='/tmp/test_shortcuts.json')
    print(f"\n✓ Manager initialized with {len(manager.shortcuts)} shortcuts")
    
    # Test loading defaults
    print("\n📋 Default Shortcuts:")
    for action, config in DEFAULT_SHORTCUTS.items():
        keys_str = ", ".join(config['keys'])
        print(f"  {action}: {keys_str} - {config['description']}")
    
    # Test categorization
    print("\n📂 Shortcuts by Category:")
    by_category = manager.get_shortcuts_by_category()
    for category, shortcuts in by_category.items():
        category_name = CATEGORIES.get(category, {}).get('name', category)
        print(f"\n  {category_name}:")
        for shortcut in shortcuts:
            keys_str = ", ".join(shortcut['keys'])
            print(f"    - {shortcut['action']}: {keys_str}")
    
    # Test conflict detection
    print("\n🔍 Testing Conflict Detection:")
    conflicts = manager.find_conflicts()
    if conflicts:
        print(f"  ⚠️  Found {len(conflicts)} conflicts:")
        for conflict in conflicts:
            print(f"    - {conflict['key']}: used by {', '.join(conflict['actions'])}")
    else:
        print("  ✓ No conflicts detected")
    
    # Test validation
    print("\n✅ Testing Key Validation:")
    test_keys = [
        ("Ctrl+S", True),
        ("Cmd+Alt+ArrowLeft", True),
        ("InvalidKey", True),  # This is actually valid as a main key
        ("Ctrl+", False),  # No main key
        ("", False),  # Empty
        ("Shift", False),  # Only modifier
    ]
    
    for key, expected_valid in test_keys:
        valid, msg = manager.validate_key_combination(key)
        status = "✓" if valid == expected_valid else "✗"
        print(f"  {status} '{key}': {msg}")
    
    # Test saving and loading
    print("\n💾 Testing Save/Load:")
    test_shortcuts = manager.shortcuts.copy()
    test_shortcuts['undo']['keys'] = ['Ctrl+U', 'Cmd+U']
    
    success = manager.save_shortcuts(test_shortcuts)
    print(f"  Save: {'✓' if success else '✗'}")
    
    # Reload
    manager2 = KeyboardShortcutManager(config_file='/tmp/test_shortcuts.json')
    if manager2.shortcuts['undo']['keys'] == ['Ctrl+U', 'Cmd+U']:
        print("  Load: ✓ (custom shortcuts loaded correctly)")
    else:
        print("  Load: ✗ (failed to load custom shortcuts)")
    
    # Test reset
    print("\n🔄 Testing Reset:")
    manager2.reset_to_defaults()
    if manager2.shortcuts['undo']['keys'] == DEFAULT_SHORTCUTS['undo']['keys']:
        print("  Reset: ✓ (reverted to defaults)")
    else:
        print("  Reset: ✗ (failed to reset)")
    
    # Clean up
    if os.path.exists('/tmp/test_shortcuts.json'):
        os.remove('/tmp/test_shortcuts.json')
        print("\n🧹 Cleanup: ✓ (removed test file)")
    
    print("\n" + "=" * 80)
    print("✓ All tests completed!")
    print("=" * 80)

if __name__ == "__main__":
    test_keyboard_shortcuts()
