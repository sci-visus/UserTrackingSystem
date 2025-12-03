"""
Test settings button click functionality
"""
import panel as pn
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from keyboard_shortcuts import KeyboardShortcutManager
from settings_modal import create_settings_button_and_modal

pn.extension()

# Initialize manager
manager = KeyboardShortcutManager(config_file='/tmp/test_shortcuts.json')

# Create button and modal
button, modal = create_settings_button_and_modal(manager)

print("=" * 80)
print("Testing Settings Button and Modal")
print("=" * 80)
print(f"Button created: {button}")
print(f"Modal created: {modal}")
print(f"Initial modal visibility: {modal.visible}")

# Simulate button click
print("\nSimulating button click...")
button.param.trigger('clicks')

print(f"Modal visibility after click: {modal.visible}")

# Create a simple app to test interactively
app = pn.Column(
    "# Settings Button Test",
    "Click the button below to open the settings modal:",
    button,
    modal,
    width=900
)

print("\nTest app created. You can serve this with:")
print("  panel serve test_settings_button.py --show")
print("=" * 80)

if __name__ == "__main__":
    app.servable()
