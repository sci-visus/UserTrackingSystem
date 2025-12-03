# Settings Button Fix - Testing Instructions

## Changes Made

### 1. Added Logging to Settings Button
- Button click now logs: `⚙️  Settings button clicked! Current modal visibility: {status}`
- Modal visibility changes are logged
- Modal creation is logged

### 2. Fixed Header Layout
- Removed nested `pn.Column` wrapper that was causing layout issues
- Settings button now directly in the header Row alongside help button

### 3. Improved Modal Positioning
- Added fixed positioning with centering
- Added semi-transparent overlay background
- Modal now appears centered on screen with proper z-index (10000)
- Max height set to 90vh to prevent overflow

### 4. Enhanced Toggle Functionality
- Better visibility management
- Overlay shows/hides with modal
- Logging at each step for debugging

## Testing Steps

1. **Restart the Docker container** to load the new code:
   ```bash
   cd /local/data/magicscan/dev_sam/ink_annotation_tool/Docker
   docker-compose restart
   ```

2. **Watch the logs** to see button click events:
   ```bash
   docker logs ink_annotation_tool -f
   ```

3. **In the browser:**
   - Refresh the annotation tool page
   - Look for the ⚙️ button in the top-right corner of the header
   - Click the ⚙️ button
   - Check the Docker logs for messages like:
     ```
     INFO:settings_modal:⚙️  Settings button clicked! Current modal visibility: False
     INFO:settings_modal:Modal visibility after toggle: True
     ```

4. **Expected behavior:**
   - Click ⚙️ button → Modal appears centered with dark overlay
   - Click again or close button → Modal disappears
   - Each click should log to Docker console

## What to Look For in Logs

### Successful Click:
```
INFO:settings_modal:Settings button and modal created with click handlers
INFO:settings_modal:⚙️  Settings button clicked! Current modal visibility: False
INFO:settings_modal:Modal visibility after toggle: True
```

### If Button Not Responding:
- Check if you see "Settings button created" in logs on page load
- Check browser console (F12) for JavaScript errors
- Verify Panel version compatibility

## Troubleshooting

### Modal not visible but logs show it's open:
- Check browser z-index conflicts
- Inspect element in browser dev tools
- Try adding `!important` to z-index style

### Button click not logging:
- Verify Panel event system is working
- Check if other buttons (help, done, etc.) log correctly
- May need to use `.param.watch` instead of `.on_click`

### Modal appears but not centered:
- Browser CSS may be overriding styles
- Check template CSS conflicts
- Try using `margin: auto` approach

## Quick Test Script

Run this to verify the button works outside the main app:
```bash
cd /local/data/magicscan/dev_sam/ink_annotation_tool/app
python test_settings_button.py
```

## Files Modified

1. `/app/settings_modal.py`
   - Added logging to toggle_modal function
   - Improved modal positioning with overlay
   - Added _show and _hide helper methods

2. `/app/annotation_tool.py`
   - Fixed header layout (removed nested Column)
   - Settings button directly in header Row

## Next Steps if Still Not Working

1. **Alternative approach**: Use Panel's built-in `Modal` template (if available in your Panel version)
2. **JavaScript approach**: Add custom JavaScript to handle modal visibility
3. **Separate page**: Make settings a separate route/page instead of modal
4. **Browser inspector**: Check if button is clickable (not hidden behind another element)

---

**To apply changes**: Restart Docker container and refresh browser
