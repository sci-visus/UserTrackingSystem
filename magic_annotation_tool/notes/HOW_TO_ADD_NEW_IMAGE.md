# How to Render Any SVS Image - Step by Step Guide

This guide shows you how to add and render any new SVS image in the annotation tool with **automatic configuration**.

## Prerequisites

- Docker and Docker Compose installed
- SVS file ready to convert
- At least 5-10 GB free disk space for DZI tiles

---

## Step 1: Place Your SVS File

Copy your SVS file to the test_data directory:

```bash
cp /path/to/your/image.svs /local/data/magicscan/ink_annotation_tool/test_data/
```

**Example:**
```bash
cp /path/to/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1.svs \
   /local/data/magicscan/ink_annotation_tool/test_data/
```

---

## Step 2: Update Conversion Script

Edit `convert_to_dzi.py` to point to your new file:

```python
# At the bottom of convert_to_dzi.py, change:
if __name__ == "__main__":
    SVS_PATH = "/data/YOUR-IMAGE-NAME.svs"  # <-- Change this
    OUTPUT_DIR = "/data/dzi_output"
    
    convert_svs_to_dzi(SVS_PATH, OUTPUT_DIR)
```

**Example:**
```python
SVS_PATH = "/data/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1.svs"
```

---

## Step 3: Rebuild Container (to pick up script changes)

```bash
cd /local/data/magicscan/ink_annotation_tool/new_tool
docker compose up --build -d
```

---

## Step 4: Convert SVS to DZI Format

Run the conversion script inside the container:

```bash
docker exec ink_annotation_tool python /app/convert_to_dzi.py
```

**What this does:**
- Converts SVS to DZI tile pyramid (takes 5-15 minutes depending on image size)
- Generates 50,000-150,000 individual tile images
- **Automatically calculates optimal viewing parameters:**
  - Start zoom level (based on image size)
  - Center position offset (based on aspect ratio)
  - Tile grid dimensions
- Saves metadata to JSON file

**Expected output:**
```
INFO:__main__:Converting /data/YOUR-IMAGE.svs to DZI format...
INFO:__main__:Slide dimensions: (137892, 40919)
INFO:__main__:Levels: 4
INFO:__main__:DZI levels: 19
...
INFO:__main__:✓ Metadata saved: /data/dzi_output/YOUR-IMAGE_metadata.json
INFO:__main__:  Recommended start level: 13
INFO:__main__:  Center offset Y multiplier: -1.5
INFO:__main__:✓ DZI conversion complete!
```

---

## Step 5: Check Generated Metadata

```bash
# View the automatically generated configuration
cat /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/YOUR-IMAGE_metadata.json
```

**Example output:**
```json
{
  "filename": "TCGA-A1-A0SE-01A-01-BS1...",
  "original_dimensions": {
    "width": 137892,
    "height": 40919
  },
  "aspect_ratio": 3.37,
  "dzi_levels": 19,
  "recommended_start_level": 13,
  "center_offset_y": -1.5,
  ...
}
```

**What the metadata means:**
- **aspect_ratio**: 3.37 means image is 3.37x wider than tall (very wide)
- **recommended_start_level**: 13 = start viewing at DZI level 13 (optimal initial zoom)
- **center_offset_y**: -1.5 = shift view up 150% to center the tissue (negative = up)

---

## Step 6: Update Annotation Tool Configuration

Edit `annotation_tool.py` to point to your new image (lines 27-29):

```python
SVS_PATH = "/data/YOUR-IMAGE-NAME.svs"
DZI_PATH = "/data/dzi_output/YOUR-IMAGE-NAME.dzi"
METADATA_PATH = "/data/dzi_output/YOUR-IMAGE-NAME_metadata.json"
```

**Example:**
```python
SVS_PATH = "/data/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1.svs"
DZI_PATH = "/data/dzi_output/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1.dzi"
METADATA_PATH = "/data/dzi_output/TCGA-A1-A0SE-01A-01-BS1.bc41fb6d-f6a5-495c-b429-80d289f0bda1_metadata.json"
```

---

## Step 7: Rebuild and Restart Application

```bash
cd /local/data/magicscan/ink_annotation_tool/new_tool
docker compose down
docker compose up --build -d
```

---

## Step 8: Access the Viewer

Open your browser and navigate to:

```
http://localhost:10556/annotation_tool
```

or

```
http://YOUR-SERVER-IP:10556/annotation_tool
```

---

## Verification

Check the Docker logs to confirm metadata was loaded:

```bash
docker logs ink_annotation_tool 2>&1 | grep -A 5 "Loaded metadata"
```

**Expected output:**
```
INFO - ✓ Loaded metadata from /data/dzi_output/YOUR-IMAGE_metadata.json
INFO -   Image dimensions: 137892x40919
INFO -   Aspect ratio: 3.37
INFO -   Recommended start level: 13
INFO -   Center offset Y: -1.5
```

---

## What Gets Configured Automatically

The system automatically adjusts these parameters based on your image:

### 1. **Start Zoom Level** (based on image size)
- **Small images** (< 20,000 px): Start at DZI level 9-10
- **Medium images** (20,000-100,000 px): Start at DZI level 11-13
- **Large images** (> 100,000 px): Start at DZI level 13-15

### 2. **Center Position** (based on aspect ratio)
- **Very wide** (aspect > 1.5): `center_offset_y = -1.5` (shift up a lot)
- **Moderately wide** (1.2 - 1.5): `center_offset_y = -1.15` (shift up)
- **Square** (0.9 - 1.2): `center_offset_y = 0.0` (no shift)
- **Tall** (< 0.9): `center_offset_y = 0.5 to 1.0` (shift down)

---

## Troubleshooting

### Issue: Tiles not loading
**Solution:** Check that DZI files exist:
```bash
ls -lh /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/
```

### Issue: Image appears off-center
**Solution:** Check the metadata's `center_offset_y` value. You can manually adjust it in `annotation_tool.py` if needed.

### Issue: Initial zoom too close/far
**Solution:** Adjust `recommended_start_level` in the metadata or pass a different value when creating the viewer.

---

## Quick Reference: File Paths

All paths use **Docker internal paths** (`/data/...`), which map to:

| Docker Path | Host Path |
|-------------|-----------|
| `/data/` | `/local/data/magicscan/ink_annotation_tool/test_data/` |
| `/app/` | `/local/data/magicscan/ink_annotation_tool/new_tool/` |

---

## Summary

The process is now **mostly universal** with only 2 manual steps:

1. **Update file path** in `convert_to_dzi.py` (Step 2)
2. **Update file path** in `annotation_tool.py` (Step 6)

Everything else (zoom levels, centering, tile serving) happens **automatically**!

---

## Example: Complete Workflow

```bash
# 1. Copy SVS file
cp /path/to/new-image.svs /local/data/magicscan/ink_annotation_tool/test_data/

# 2. Edit convert_to_dzi.py (update SVS_PATH)
# 3. Rebuild container
cd /local/data/magicscan/ink_annotation_tool/new_tool
docker compose up --build -d

# 4. Convert to DZI
docker exec ink_annotation_tool python /app/convert_to_dzi.py

# 5. View metadata
cat /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/new-image_metadata.json

# 6. Edit annotation_tool.py (update SVS_PATH, DZI_PATH, METADATA_PATH)

# 7. Rebuild and restart
docker compose down && docker compose up --build -d

# 8. Open http://localhost:10556/annotation_tool
```

Done! 🎉
