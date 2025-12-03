## Data Flow: SVS to Annotation Tool

### Overview

The annotation tool displays SVS (Aperio ScanScope Virtual Slide) files by converting them to DZI (Deep Zoom Image) format and serving the tiles through a multi-tier architecture.

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. SOURCE DATA                                                      │
│    /local/data/magicscan/ink_annotation_tool/test_data/            │
│    └── TCGA-*.svs (original whole slide images)                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. CONVERSION (convert_to_dzi.py)                                  │
│    Uses OpenSlide to read SVS files                                │
│    Generates image pyramid with multiple zoom levels               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. DZI OUTPUT                                                       │
│    /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/ │
│    ├── {filename}.dzi (XML metadata)                               │
│    ├── {filename}_files/                                           │
│    │   ├── 0/0_0.png (lowest resolution - 1 tile)                 │
│    │   ├── 1/0_0.png, 0_1.png, ... (4 tiles)                      │
│    │   ├── ...                                                      │
│    │   └── 13/... (highest resolution - thousands of tiles)       │
│    └── {filename}_metadata.json (custom display settings)         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. DOCKER VOLUME MOUNT                                             │
│    Host: /local/data/.../test_data                                 │
│    Container: /data                                                 │
│    Container: /data/dzi_output                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. DZI TILE SERVER (Flask - Port 10557)                           │
│    File: dzi_server.py                                             │
│    - Serves static PNG tiles from /data/dzi_output                │
│    - URL: http://localhost:10557/{filename}_files/{z}/{x}_{y}.png │
│    - Provides directory listing at root                            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. PANEL APPLICATION (Port 10556)                                  │
│    File: annotation_tool.py                                        │
│    Class: AnnotationApp                                            │
│    ├── Scans /data/*.svs files                                    │
│    ├── Creates dropdown selector                                   │
│    └── On selection: creates SVSAnnotationTool                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 7. SVS ANNOTATION TOOL                                             │
│    Class: SVSAnnotationTool                                        │
│    ├── Opens SVS with OpenSlide                                    │
│    ├── Reads metadata JSON                                         │
│    ├── Calculates zoom levels and dimensions                       │
│    └── Creates SVSLeafletViewer                                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 8. LEAFLET VIEWER (Browser JavaScript)                            │
│    Class: SVSLeafletViewer (ReactiveHTML)                         │
│    ├── Initializes Leaflet map                                    │
│    ├── Creates DZITileLayer with tile URL pattern                 │
│    ├── Configures zoom levels and bounds                          │
│    └── Adds MiniMap overview control                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 9. TILE LOADING (Browser)                                          │
│    Leaflet requests tiles as user pans/zooms:                     │
│    GET http://localhost:10557/TCGA-*_files/11/5_3.png            │
│    GET http://localhost:10557/TCGA-*_files/11/5_4.png            │
│    GET http://localhost:10557/TCGA-*_files/11/6_3.png            │
│    ... (only visible tiles are loaded)                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Detailed Step-by-Step Process

#### Step 1: SVS File Discovery
```python
# annotation_tool.py - AnnotationApp.__init__()
def __init__(self):
    self.svs_files = glob.glob("/data/*.svs")
    # Example: ['/data/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1.svs']
    
    self.image_selector = pn.widgets.Select(
        name='Select Image',
        options={os.path.basename(f): f for f in self.svs_files}
    )
```

#### Step 2: Image Selection & Loading
```python
# annotation_tool.py - AnnotationApp._on_selection_change()
def _on_selection_change(self, event):
    svs_path = event.new  # Full path to selected SVS
    self._load_image(svs_path)

def _load_image(self, svs_path):
    # Creates new SVSAnnotationTool instance
    self.current_tool = SVSAnnotationTool(svs_path)
```

#### Step 3: SVS Metadata Reading
```python
# annotation_tool.py - SVSAnnotationTool.__init__()
def __init__(self, svs_path):
    # Open SVS file with OpenSlide
    self.slide = openslide.OpenSlide(svs_path)
    self.dimensions = self.slide.dimensions  # e.g., (137892, 40919)
    self.level_count = self.slide.level_count  # e.g., 4
    
    # Load custom metadata
    metadata_path = self._get_metadata_path()
    with open(metadata_path, 'r') as f:
        self.metadata = json.load(f)
    
    # Extract display parameters
    self.start_level = self.metadata['recommended_start_level']  # e.g., 13
    self.center_offset_y = self.metadata['center_offset_y']  # e.g., -1.5
```

#### Step 4: DZI Path Construction
```python
# annotation_tool.py - SVSAnnotationTool._get_dzi_path()
def _get_dzi_path(self):
    base_name = os.path.splitext(os.path.basename(self.svs_path))[0]
    # e.g., "TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1"
    
    dzi_path = f"/data/dzi_output/{base_name}.dzi"
    # Path to DZI XML file in container
    return dzi_path
```

#### Step 5: Viewer Creation
```python
# annotation_tool.py - SVSAnnotationTool.create_dashboard()
def create_dashboard(self):
    dzi_url = f"http://{{{{window.location.hostname}}}}:10557/{base_name}.dzi"
    # JavaScript will replace {{window.location.hostname}} with actual host
    
    viewer = SVSLeafletViewer(
        dzi_url=dzi_url,
        width_px=width,
        height_px=height,
        max_zoom=max_zoom,
        start_level=start_level,
        center_offset_y=center_offset_y
    )
```

#### Step 6: Leaflet Map Initialization
```javascript
// annotation_tool.py - SVSLeafletViewer._scripts['after_layout']

// Extract base name from DZI URL
const dziUrl = data.dzi_url;  
// e.g., "http://olympus.sci.utah.edu:10557/TCGA-*.dzi"

const dziBaseName = dziUrl.split('/').pop().replace('.dzi', '');
// e.g., "TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1"

// Create Leaflet map
state.map = L.map(map_div, {
    crs: L.CRS.Simple,  // Non-geographic coordinate system
    center: [centerY, centerX],
    zoom: 0,
    maxZoom: maxZoom
});
```

#### Step 7: DZI Tile Layer Setup
```javascript
// annotation_tool.py - Custom DZITileLayer definition

class DZITileLayer extends L.TileLayer {
    getTileUrl(coords) {
        const dziZoom = this.options.maxNativeZoom - coords.z + 11;
        const baseUrl = 'http://' + window.location.hostname + ':10557/' + dziBaseName + '_files';
        const url = baseUrl + '/' + dziZoom + '/' + coords.x + '_' + coords.y + '.png';
        
        // Example URL:
        // http://olympus.sci.utah.edu:10557/TCGA-*_files/13/5_3.png
        //                                   │              │  │ │ │
        //                                   │              │  │ │ └─ tile Y
        //                                   │              │  │ └─── tile X  
        //                                   │              │  └───── zoom level
        //                                   │              └──────── tile directory
        //                                   └─────────────────────── base name
        
        return url;
    }
}

// Create and add tile layer
state.tileLayer = new DZITileLayer('', {
    tileSize: 257,
    noWrap: true,
    minNativeZoom: 0,
    maxNativeZoom: maxZoom - 11
}).addTo(state.map);
```

#### Step 8: Tile Request Flow
```
Browser                 Flask Server              File System
   │                         │                         │
   │ GET /TCGA-*_files/     │                         │
   │   13/5_3.png           │                         │
   ├────────────────────────>│                         │
   │                         │ Read file from:         │
   │                         │ /data/dzi_output/       │
   │                         │   TCGA-*_files/13/      │
   │                         │   5_3.png               │
   │                         ├─────────────────────────>│
   │                         │<─────────────────────────┤
   │                         │ Return PNG image        │
   │<────────────────────────┤                         │
   │ Display tile in canvas  │                         │
   │                         │                         │
```

#### Step 9: Image Switching
```python
# annotation_tool.py - AnnotationApp._on_selection_change()

def _on_selection_change(self, event):
    # User selects different image from dropdown
    
    # 1. Load new image
    self._load_image(event.new)  # Creates new SVSAnnotationTool
    
    # 2. Get new dashboard with viewer
    new_dashboard = self.current_tool.create_dashboard()
    new_viewer = new_dashboard.main[0]
    
    # 3. Update existing viewer parameters
    old_viewer = self.template.main[0]
    old_viewer.param.update(**{
        'dzi_url': new_viewer.dzi_url,  # New DZI URL
        'width_px': new_viewer.width_px,
        'height_px': new_viewer.height_px,
        'max_zoom': new_viewer.max_zoom,
        'start_level': new_viewer.start_level,
        'center_offset_y': new_viewer.center_offset_y,
        'reload_counter': old_viewer.reload_counter + 1  # Triggers re-render
    })
    
    # 4. Update sidebar (image info, minimap)
    self.template.sidebar.objects = selector + new_sidebar_items
```

### Key Configuration Files

#### docker-compose.yml
```yaml
services:
  annotation-tool:
    volumes:
      # Mount host directory to container
      - /local/data/magicscan/ink_annotation_tool/test_data:/data
      - /local/data/magicscan/ink_annotation_tool/test_data/dzi_output:/data/dzi_output
    ports:
      - "10556:10556"  # Panel app
      - "10557:10557"  # Tile server
```

#### start.sh
```bash
#!/bin/bash
# Start DZI tile server
python dzi_server.py &

# Start Panel application
panel serve annotation_tool.py --address 0.0.0.0 --port 10556 \
  --allow-websocket-origin "*" --show
```

#### dzi_server.py
```python
from flask import Flask, send_from_directory

app = Flask(__name__)
DZI_BASE_DIR = "/data/dzi_output"

@app.route('/<path:filename>')
def serve_file(filename):
    return send_from_directory(DZI_BASE_DIR, filename)

app.run(host='0.0.0.0', port=10557)
```

### Tile URL Pattern Explained

For a DZI file at zoom level 13, tile coordinates (5, 3):

```
http://olympus.sci.utah.edu:10557/TCGA-A1-A0SE-01A-01-BS1_files/13/5_3.png
│                              │  │                                   │  │ │
│                              │  │                                   │  │ └─ Tile Y coordinate
│                              │  │                                   │  └─── Tile X coordinate
│                              │  │                                   └────── DZI zoom level
│                              │  └──────────────────────────────────────── Tile directory
│                              └─────────────────────────────────────────── Base filename
└────────────────────────────────────────────────────────────────────────── Server host:port
```

The tile directory structure on disk:
```
/data/dzi_output/TCGA-A1-A0SE-01A-01-BS1_files/
├── 0/
│   └── 0_0.png          (entire image, 1 tile)
├── 1/
│   ├── 0_0.png          (4 tiles)
│   ├── 0_1.png
│   ├── 1_0.png
│   └── 1_1.png
├── ...
└── 13/
    ├── 0_0.png          (thousands of tiles at full resolution)
    ├── 0_1.png
    ├── ...
    ├── 5_3.png          ← This tile gets served
    └── ...
```

### Performance Optimizations

1. **Lazy Loading**: Only tiles in the current viewport are requested
2. **Tile Caching**: Browser caches tiles automatically
3. **Pyramid Structure**: Lower resolution tiles load first for quick preview
4. **Efficient Serving**: Flask serves static files directly from disk
5. **No Processing**: Pre-generated tiles avoid runtime image processing

### Debugging Data Flow

To verify each step:

```bash
# 1. Check SVS files are present
ls -lh /local/data/magicscan/ink_annotation_tool/test_data/*.svs

# 2. Check DZI files were generated
ls -lh /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/

# 3. Check tile directories exist
ls -lh /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/TCGA-*_files/

# 4. Verify tile server is running
curl http://localhost:10557/health

# 5. Test tile URL directly
curl -I http://localhost:10557/TCGA-A1-A0SE-01A-01-BS1_files/13/0_0.png

# 6. Check Panel app logs
docker logs -f ink_annotation_tool | grep "SELECTION CHANGE"

# 7. Monitor tile requests in browser
# Open DevTools → Network tab → Filter by "png"
```

This flow ensures efficient delivery of gigapixel images by breaking them into manageable tiles that are served on-demand as the user navigates the slide.