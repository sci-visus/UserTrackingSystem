# SVS Annotation Tool with Interactive DZI Viewer

A web-based whole slide image (WSI) annotation tool built with Panel and Leaflet for viewing and annotating large histopathology images in Deep Zoom Image (DZI) format.

## Features

### 🔬 Image Viewing
- **Deep Zoom Image (DZI) Support**: Efficient tiled viewing of gigapixel whole slide images
- **Interactive Pan & Zoom**: Smooth navigation using Leaflet mapping library
- **Multi-Image Support**: Switch between multiple SVS/DZI files via dropdown selector
- **Real-time Zoom Tracking**: Current zoom level display with magnification (e.g., "1x", "10x")
- **Custom Scale Bar**: Automatic unit conversion (nm, μm, mm, cm) based on zoom level
- **MiniMap Overview**: Interactive overlay minimap in bottom-right corner showing:
  - Current viewport position (red rectangle)
  - Click-to-navigate functionality
  - Toggle button to minimize/expand (◀)
  - Entire slide overview at fixed zoom level

### 📊 Image Information Display
- **Automatic Metadata Loading**: Reads dimensions, pyramid levels, and tile information
- **Smart Centering**: Uses metadata to properly center different tissue types
- **Dynamic Updates**: Information panel updates when switching between images

### 🎨 Annotation Tools
- **Freehand Drawing**: Natural pen/brush style annotation
  - Click button (✏️) to activate
  - Or hold Shift key for temporary drawing mode
  - Yellow polyline with smooth drawing
- **Keyboard Shortcuts**:
  - Delete/Backspace: Remove selected drawings
  - Shift + Drag: Freehand drawing mode
- **Edit & Delete**: Modify or remove existing annotations

### 🎛️ Controls
- **Mouse Wheel**: Zoom in/out
- **Click + Drag**: Pan around the image
- **Double Click**: Zoom in
- **+/- Buttons**: Manual zoom controls with magnification display
- **MiniMap**: Click to jump to different areas, toggle to collapse
- **Shift Key**: Hold while dragging to draw freehand
- **Delete/Backspace**: Remove selected drawings

## Architecture

### Project Structure

```
new_tool/
├── app/                         # Python application code
│   ├── annotation_tool.py       # Main Panel application
│   ├── dzi_server.py            # Flask server for DZI tiles
│   └── convert_to_dzi.py        # SVS to DZI conversion utility
├── Features/                    # JavaScript feature modules
│   ├── freehand_drawing.js      # Freehand drawing functionality
│   ├── scale_bar.js             # Custom scale bar with units
│   └── minimap_overview.js      # MiniMap with embedded library
├── Docker/                      # Docker configuration
│   ├── Dockerfile               # Container definition
│   ├── docker-compose.yml       # Service orchestration
│   ├── requirements.txt         # Python dependencies
│   └── start.sh                 # Container startup script
├── notes/                       # Documentation
│   ├── Data_source_flow.md
│   ├── HOW_TO_ADD_NEW_IMAGE.md
│   └── IMAGE_SELECTOR_GUIDE.md
└── README.md                    # This file
```

### Data Directory Structure
```
/local/data/magicscan/dzi_datasets/new_data/
└── dzi_output/                  # Mounted in container as /data/dzi_output
    ├── {filename}.dzi           # DZI XML metadata
    ├── {filename}_files/        # Tile pyramid directory
    └── {filename}_metadata.json # Custom metadata
```

### Services

1. **Panel App (Port 10556)**: Main web interface
   - Serves the annotation tool UI
   - Handles user interactions
   - Manages image switching and viewer updates

2. **DZI Tile Server (Port 10557)**: Static file server
   - Serves DZI tile images (PNG files)
   - Provides directory browsing at `http://localhost:10557/`
   - Health check endpoint: `http://localhost:10557/health`

### Technology Stack

- **Backend**: Python 3.11
  - Panel (HoloViz) - Web app framework
  - Flask - Tile server
  - OpenSlide - SVS file reading
  - Pillow (PIL) - Image processing

- **Frontend**: JavaScript (modular architecture)
  - Leaflet 1.7.1 - Interactive maps (CDN)
  - Custom DZI Tile Layer - Deep Zoom Image support
  - Freehand Drawing Module - Natural drawing with button/Shift key
  - Scale Bar Module - Auto-unit conversion (nm→μm→mm→cm)
  - MiniMap Module - Embedded Leaflet-MiniMap library + initialization

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- SVS whole slide image files
- At least 8GB RAM recommended for large images

### Step 1: Prepare Data Directory

```bash
mkdir -p /local/data/magicscan/ink_annotation_tool/test_data/dzi_output
```

Place your SVS files in:
```
/local/data/magicscan/ink_annotation_tool/test_data/
```

### Step 2: Convert SVS to DZI

Use the conversion utility inside the container:
```bash
docker exec ink_annotation_tool python /main_app/app/convert_to_dzi.py
```

This will create:
- DZI XML files: `{filename}.dzi`
- Tile directories: `{filename}_files/`
- Metadata JSON: `{filename}_metadata.json`

### Step 3: Build and Run

```bash
cd /local/data/magicscan/ink_annotation_tool/new_tool/Docker
docker compose down
docker compose up --build -d
```

**Note**: Docker commands must be run from the `Docker/` folder.

### Step 4: Access the Tool

- **Main Application**: http://localhost:10556/ or http://your-server:10556/
- **Tile Browser**: http://localhost:10557/
- **Health Check**: http://localhost:10557/health

## Usage Guide

### Viewing Images

1. **Select Image**: Use the dropdown at the top of the sidebar
2. **Navigate**: 
   - Drag to pan
   - Scroll wheel to zoom
   - Double-click to zoom in
3. **Use MiniMap**: 
   - View your position on the overview
   - Click to jump to different areas
   - Toggle minimize button (▼/▲)

### Drawing Annotations

1. **Freehand Drawing**:
   - Click the ✏️ button in the top-right corner to activate
   - Or hold the Shift key while dragging to draw temporarily
   - Draw naturally with mouse or pen/stylus
   - Yellow lines with smooth rendering

2. **Editing Annotations**:
   - Click on an existing drawing to select it
   - Press Delete or Backspace to remove selected drawing
   - Drawings are stored in a feature group layer

3. **Drawing Tips**:
   - Button stays active (red background) until clicked again
   - Shift key provides temporary drawing mode
   - Release Shift to return to pan mode
   - Cursor changes to pen icon when in drawing mode

### Customizing Metadata

You can manually edit metadata files to adjust viewer behavior:

```bash
# Edit metadata
nano /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/{filename}_metadata.json
```

Key parameters:
```json
{
  "recommended_start_level": 13,      // Starting zoom level
  "center_offset_y": -1.5,            // Y-axis centering adjustment
  "dimensions_at_start_level": [      // Display dimensions
    40919,
    137892
  ],
  "tiles_at_start_level": {           // Tile counts
    "x": 160,
    "y": 537
  }
}
```

After editing, restart the container:
```bash
docker compose restart
```

## File Permissions

The container automatically sets permissions on startup to allow local editing:

```bash
chmod -R 777 /data/dzi_output
```

This allows you to edit metadata files from your host machine without permission errors.

## DZI Tile Structure

```
{filename}_files/
├── 0/           # Lowest resolution (1 tile)
│   └── 0_0.png
├── 1/           # Next level
│   ├── 0_0.png
│   └── ...
├── ...
└── 13/          # Highest resolution (many tiles)
    ├── 0_0.png
    ├── 0_1.png
    ├── 1_0.png
    └── ... (thousands of tiles)
```

Each level doubles the resolution. Level 0 is the entire image in one tile, while the highest level provides full resolution detail.

## Troubleshooting

### Image Not Displaying

1. **Check DZI files exist**:
   ```bash
   ls -la /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/
   ```

2. **Verify tile server is running**:
   ```bash
   curl http://localhost:10557/health
   ```

3. **Check logs**:
   ```bash
   docker logs -f ink_annotation_tool
   ```

### Image Not Switching

If switching from image 2 back to image 1 doesn't work:
1. Check browser console (F12) for JavaScript errors
2. Verify the reload_counter is incrementing in logs
3. Try refreshing the browser page

### MiniMap Not Showing

The MiniMap is embedded inline to avoid CORS issues. If it's not appearing:
1. Check browser console for "✓ MiniMap overlay added to map"
2. Look for the minimap in the bottom-right corner
3. Try toggling it with the ◀ button
4. Check if it's minimized to a small rectangle
5. Verify `minimap_overview.js` is loaded in browser DevTools

### Freehand Drawing Not Working

If freehand drawing doesn't work:
1. Check browser console for "initializeFreehandDrawing function not found"
2. Verify the ✏️ button appears in top-right corner
3. Try using Shift+Drag as alternative
4. Check if `freehand_drawing.js` loaded correctly

### Scale Bar Not Displaying

If the scale bar is missing:
1. Check browser console for "initializeScaleBar function not found"
2. Look in bottom-left corner for the scale indicator
3. Verify `scale_bar.js` is loaded

### Permission Denied When Editing Metadata

```bash
# Fix manually if needed
chmod 777 /local/data/magicscan/dzi_datasets/new_data/dzi_output/*.json
```

### Module Loading Issues

All JavaScript modules are inlined at runtime:
- No CORS issues since code is embedded
- Check Python file can read from `Features/` folder
- Verify relative paths: `os.path.join(os.path.dirname(__file__), '..', 'Features', ...)`

### Port Already in Use

If ports 10556 or 10557 are already taken:

```bash
# Edit docker-compose.yml to use different ports
ports:
  - "10558:10556"  # Use 10558 instead
  - "10559:10557"  # Use 10559 instead
```

## Development

### Modifying the Application

1. **Edit Python files**: Modify files in `app/` directory
2. **Edit Features**: Modify JavaScript modules in `Features/` directory
3. **Edit Docker config**: Modify files in `Docker/` directory
4. Rebuild and restart:
   ```bash
   cd /local/data/magicscan/ink_annotation_tool/new_tool/Docker
   docker compose down
   docker compose up --build -d
   ```

### Adding New Features

The application uses a modular architecture:

**Python (Panel ReactiveHTML):**
- `app/annotation_tool.py`: Main application with viewer component
  - **Parameters**: Define reactive properties at the class level
  - **_template**: HTML structure with Leaflet div
  - **_scripts**: JavaScript for map initialization
  - Features are loaded as inline modules from `Features/` folder

**JavaScript Modules (`Features/`):**
- `freehand_drawing.js`: Exports `initializeFreehandDrawing(map, drawnItems)`
- `scale_bar.js`: Exports `initializeScaleBar(map, mmPerPixel, startLevel, maxZoom)`
- `minimap_overview.js`: Includes L.Control.MiniMap library + `initializeMiniMap()`

**To add a new feature:**
1. Create `Features/my_feature.js` with initialization function
2. Add inline loading in `annotation_tool.py` _scripts
3. Call the initialization function after map creation

### Debugging

View real-time logs:
```bash
docker logs -f ink_annotation_tool
```

Filter for specific events:
```bash
docker logs -f ink_annotation_tool 2>&1 | grep "SELECTION CHANGE"
```

Enter the container:
```bash
docker exec -it ink_annotation_tool bash
```

## Performance Tips

1. **DZI Conversion**: Use appropriate tile size (254-512px) and compression
2. **Memory**: Allocate sufficient RAM for Docker (8GB+ recommended)
3. **Storage**: DZI files can be 2-3x the size of original SVS
4. **Network**: Host on a fast network connection for remote access
5. **Browser**: Use Chrome or Firefox for best Leaflet performance

## Known Limitations

- Annotations are not persisted (in-memory only)
- No user authentication or multi-user support
- Single annotation layer (no categories/classes)
- Only freehand drawing available (no polygons, rectangles, circles)
- No measurement tools (distance, area)
- Limited to DZI format (must convert from SVS)
- Box zoom disabled (Shift+Drag used for freehand drawing)

## Future Enhancements

Potential improvements:
- [ ] Save/load annotations to JSON or database
- [ ] Multi-layer annotations with categories/labels
- [ ] Additional drawing tools (polygon, rectangle, circle)
- [ ] Measurement tools (rulers, area calculation with scale)
- [ ] Export annotations to common formats (GeoJSON, ASAP XML, QuPath)
- [ ] User authentication and project management
- [ ] Real-time collaboration features
- [ ] AI-assisted annotation tools (auto-segmentation)
- [ ] Support for additional formats (TIFF, JPEG2000, OME-TIFF)
- [ ] Annotation undo/redo functionality
- [ ] Drawing properties (color, thickness, opacity)

## License

[Specify your license here]

## Contact

[Your contact information]

## Acknowledgments

- OpenSlide for SVS reading capabilities
- Panel/HoloViz for the web framework
- Leaflet for the interactive mapping library
- TCGA for example whole slide images# magic_annotation_tool
