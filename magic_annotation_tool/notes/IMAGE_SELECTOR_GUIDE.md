# Image Selector Feature - Quick Guide

## Overview

The annotation tool now includes a **dropdown selector** to switch between multiple SVS images without restarting the application!

## Features

✅ **Auto-detect all DZI images** in `/data/dzi_output/`  
✅ **Display image information** (dimensions, aspect ratio)  
✅ **Switch between images** with one click  
✅ **Automatic configuration** (zoom level, centering) per image  
✅ **Real-time loading** - no server restart needed

---

## How to Use

### 1. Open the Annotation Tool

Navigate to: `http://localhost:10556/annotation_tool`

### 2. Select an Image

At the top of the sidebar, you'll see:

```
┌────────────────────────────────────┐
│ Image Selector                     │
├────────────────────────────────────┤
│ Select Image:                      │
│ [TCGA-A1-A0SE-01A-01-BS1...     ▼] │
├────────────────────────────────────┤
│ Available Images                   │
│                                    │
│ Current: TCGA-A1-A0SE...          │
│ Size: 137,892 x 40,919 px         │
│ Aspect Ratio: 3.37                │
└────────────────────────────────────┘
```

### 3. Switch Images

Click the dropdown and select a different image. The viewer will:
- Load the new image automatically
- Apply the correct zoom level
- Apply the correct centering
- Update the thumbnail
- Display new image info

---

## Available Images (Current)

### Image 1: TCGA-A1-A0SE-01A-01-BS1
- **Dimensions:** 137,892 × 40,919 pixels
- **Aspect Ratio:** 3.37 (very wide)
- **Recommended Start Level:** 13
- **Center Offset:** -1.5 (shifts up significantly)
- **DZI Tiles:** 115,076 tiles

### Image 2: TCGA-E9-A1RG-01Z-00-DX1
- **Dimensions:** 93,296 × 71,112 pixels
- **Aspect Ratio:** 1.31 (moderately wide)
- **Recommended Start Level:** 13
- **Center Offset:** -1.15 (shifts up moderately)
- **DZI Tiles:** 135,531 tiles

---

## Adding More Images

To add a new image to the selector:

### Step 1: Convert SVS to DZI

```bash
# Edit convert_to_dzi.py to point to your new image
# Then run:
docker exec ink_annotation_tool python /app/convert_to_dzi.py
```

### Step 2: Refresh the Page

The image selector will **automatically detect** the new DZI file!

No need to:
- ❌ Restart the container
- ❌ Edit annotation_tool.py
- ❌ Rebuild anything

Just refresh your browser! 🎉

---

## Technical Details

### How It Works

1. **On page load**, the app scans `/data/dzi_output/` for all `.dzi` files
2. **Reads metadata** from `{image_name}_metadata.json` if available
3. **Creates dropdown** with shortened display names
4. **On selection change**:
   - Closes current slide
   - Loads new slide with OpenSlide
   - Reads new metadata
   - Initializes new viewer with correct parameters
   - Updates sidebar info

### Metadata Used

Each image's metadata JSON contains:
```json
{
  "recommended_start_level": 13,
  "center_offset_y": -1.5,
  "dzi_levels": 19,
  "aspect_ratio": 3.37,
  "dimensions_at_start_level": {
    "width": 4309.12,
    "height": 1278.72
  }
}
```

These values are **automatically applied** when you switch images.

---

## Troubleshooting

### Issue: Image not appearing in dropdown

**Check:**
```bash
# Verify DZI file exists
ls -l /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/*.dzi

# Verify SVS file exists
ls -l /local/data/magicscan/ink_annotation_tool/test_data/*.svs
```

### Issue: Image appears but won't load

**Check metadata:**
```bash
cat /local/data/magicscan/ink_annotation_tool/test_data/dzi_output/YOUR-IMAGE_metadata.json
```

**Generate metadata if missing:**
```bash
docker exec ink_annotation_tool python -c "
from convert_to_dzi import calculate_viewer_metadata
import openslide
from openslide import deepzoom
import json

slide = openslide.OpenSlide('/data/YOUR-IMAGE.svs')
dz = deepzoom.DeepZoomGenerator(slide, tile_size=256, overlap=1)
metadata = calculate_viewer_metadata(slide, dz, 'YOUR-IMAGE')

with open('/data/dzi_output/YOUR-IMAGE_metadata.json', 'w') as f:
    json.dump(metadata, f, indent=2)

print('Metadata generated!')
slide.close()
"
```

### Issue: Dropdown shows truncated names

This is normal for long filenames. The full name is used internally, only the display is shortened.

---

## Future Enhancements

Possible additions:
- 🔍 Search/filter images by name
- 📊 Sort by size, date, aspect ratio
- 🖼️ Thumbnail previews in dropdown
- 📁 Folder organization
- 🏷️ Tags and categories
- ⭐ Favorites/bookmarks

---

## Summary

The **Image Selector** makes it easy to work with multiple SVS images:

1. **Convert once** with `convert_to_dzi.py`
2. **Select from dropdown**
3. **Switch anytime** - no restart needed
4. **Automatic configuration** for each image

Enjoy your multi-image annotation tool! 🎨
