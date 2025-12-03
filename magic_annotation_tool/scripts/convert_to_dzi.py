import openslide
from openslide import deepzoom
import os
import logging
import json
import sys
from multiprocessing import Pool, cpu_count
from functools import partial

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_tile_worker(args):
    """Worker function to save a single tile"""
    level, col, row, tiles_dir, svs_path, tile_size, overlap = args
    try:
        # Each worker opens its own slide instance
        slide = openslide.OpenSlide(svs_path)
        dz = deepzoom.DeepZoomGenerator(slide, tile_size=tile_size, overlap=overlap, limit_bounds=True)
        
        # Generate and save tile
        tile = dz.get_tile(level, (col, row))
        tile_path = os.path.join(tiles_dir, str(level), f"{col}_{row}.png")
        tile.save(tile_path, format='PNG')
        
        slide.close()
        return True
    except Exception as e:
        logger.error(f"Failed to generate tile {level}/{col}_{row}: {e}")
        return False

def convert_svs_to_dzi(svs_path, output_dir, tile_size=256, overlap=1, num_workers=None):
    """
    Convert SVS file to DZI format with parallel tile generation
    
    Args:
        svs_path: Path to SVS file
        output_dir: Directory to save DZI files
        tile_size: Size of each tile (default 256)
        overlap: Overlap between tiles (default 1)
        num_workers: Number of parallel workers (default: CPU count)
    """
    if num_workers is None:
        num_workers = cpu_count()
    
    logger.info(f"Converting {svs_path} to DZI format...")
    logger.info(f"  Using {num_workers} parallel workers")
    
    # Open slide
    slide = openslide.OpenSlide(svs_path)
    
    # Get base filename
    base_name = os.path.splitext(os.path.basename(svs_path))[0]
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Create DeepZoomGenerator
    dz = deepzoom.DeepZoomGenerator(
        slide, 
        tile_size=tile_size, 
        overlap=overlap,
        limit_bounds=True
    )
    
    logger.info(f"Slide dimensions: {slide.dimensions}")
    logger.info(f"Levels: {slide.level_count}")
    logger.info(f"DZI levels: {dz.level_count}")
    
    # Save DZI descriptor (XML file) and tiles
    dzi_file = os.path.join(output_dir, f"{base_name}.dzi")
    tiles_dir = os.path.join(output_dir, f"{base_name}_files")
    
    logger.info(f"Saving DZI tiles to {output_dir}...")
    
    # Create DZI XML descriptor file
    with open(dzi_file, 'w') as f:
        f.write(dz.get_dzi('png'))
    
    logger.info(f"✓ DZI descriptor saved: {dzi_file}")
    
    # Generate all tiles in parallel
    os.makedirs(tiles_dir, exist_ok=True)
    
    # Create level directories first
    for level in range(dz.level_count):
        level_dir = os.path.join(tiles_dir, str(level))
        os.makedirs(level_dir, exist_ok=True)
    
    # Build list of all tiles to generate
    tile_coords = []
    total_tiles = 0
    for level in range(dz.level_count):
        cols, rows = dz.level_tiles[level]
        level_tiles = cols * rows
        total_tiles += level_tiles
        logger.info(f"  Level {level}: {cols}x{rows} = {level_tiles} tiles")
        
        for col in range(cols):
            for row in range(rows):
                tile_coords.append((level, col, row, tiles_dir, svs_path, tile_size, overlap))
    
    logger.info(f"  Generating {total_tiles} tiles in parallel...")
    
    # Generate tiles using multiprocessing
    with Pool(processes=num_workers) as pool:
        results = []
        for i, result in enumerate(pool.imap_unordered(save_tile_worker, tile_coords), 1):
            results.append(result)
            if i % 100 == 0 or i == total_tiles:
                logger.info(f"    Progress: {i}/{total_tiles} tiles ({i*100//total_tiles}%)")
    
    success_count = sum(results)
    logger.info(f"  Successfully generated {success_count}/{total_tiles} tiles")
    
    # Calculate optimal viewing parameters and save metadata
    metadata = calculate_viewer_metadata(slide, dz, base_name)
    metadata_file = os.path.join(output_dir, f"{base_name}_metadata.json")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"✓ Metadata saved: {metadata_file}")
    logger.info(f"✓ DZI conversion complete!")
    logger.info(f"  Total tiles generated: {total_tiles}")
    logger.info(f"  DZI file: {dzi_file}")
    logger.info(f"  Tiles directory: {tiles_dir}")
    logger.info(f"  Recommended start level: {metadata['recommended_start_level']}")
    logger.info(f"  Center offset Y multiplier: {metadata['center_offset_y']}")
    
    slide.close()
    return dzi_file, metadata

def calculate_viewer_metadata(slide, dz, base_name):
    """
    Calculate optimal viewer parameters based on image characteristics
    
    Args:
        slide: OpenSlide object
        dz: DeepZoomGenerator object
        base_name: Base filename
        
    Returns:
        dict: Metadata including optimal start level and center offset
    """
    width, height = slide.dimensions
    aspect_ratio = width / height
    dzi_levels = dz.level_count
    
    logger.info(f"Calculating optimal viewer settings...")
    logger.info(f"  Image dimensions: {width} × {height} pixels")
    logger.info(f"  Aspect ratio: {aspect_ratio:.3f}:1")
    logger.info(f"  DZI levels: {dzi_levels}")
    
    # Fixed start level for all images
    recommended_start_level = 10
    
    # Calculate dimensions at default start level for backwards compatibility
    scale_factor = 2 ** (dzi_levels - 1 - recommended_start_level)
    width_at_start = width / scale_factor
    height_at_start = height / scale_factor
    
    # Calculate center offset based on aspect ratio
    # For wider images (aspect > 1.3), shift up more
    # For taller images (aspect < 0.8), shift down
    if aspect_ratio > 1.5:
        # Very wide images - shift up significantly
        center_offset_y = -1.25
    elif aspect_ratio > 1.2:
        # Moderately wide images
        center_offset_y = -1.15
    elif aspect_ratio > 0.9:
        # Nearly square images
        center_offset_y = 0.0
    elif aspect_ratio > 0.7:
        # Moderately tall images
        center_offset_y = 0.5
    else:
        # Very tall images
        center_offset_y = 1.0
    
    # Calculate tile grid size at start level
    cols, rows = dz.level_tiles[recommended_start_level]
    
    metadata = {
        "filename": base_name,
        "original_dimensions": {
            "width": width,
            "height": height
        },
        "aspect_ratio": round(aspect_ratio, 3),
        "dzi_levels": dzi_levels,
        "recommended_start_level": recommended_start_level,
        "dimensions_at_start_level": {
            "width": round(width_at_start, 2),
            "height": round(height_at_start, 2)
        },
        "tiles_at_start_level": {
            "cols": cols,
            "rows": rows
        },
        "center_offset_y": center_offset_y,
        "tile_size": 256,
        "overlap": 1
    }
    
    return metadata

if __name__ == "__main__":
    # Detect if running inside container or locally
    if os.path.exists("/data/test_data"):
        # Running inside container
        svs_dir = "/data/test_data"
        output_dir = "/data/dzi_output"
    else:
        # Running locally
        script_dir = os.path.dirname(os.path.abspath(__file__))
        svs_dir = os.path.join(script_dir, "datasets")
        output_dir = os.path.join(svs_dir, "dzi_output")
    
    print(f"SVS directory: {svs_dir}")
    print(f"Output directory: {output_dir}")
    
    # Check if directory exists
    if not os.path.exists(svs_dir):
        logger.error(f"SVS directory not found: {svs_dir}")
        sys.exit(1)
    
    # Find all SVS files in the directory
    svs_files = [f for f in os.listdir(svs_dir) if f.endswith('.svs')]
    
    if not svs_files:
        logger.error(f"No SVS files found in {svs_dir}")
        sys.exit(1)
    
    logger.info(f"Found {len(svs_files)} SVS file(s) to convert")
    
    # Convert each SVS file
    for svs_file in svs_files:
        svs_path = os.path.join(svs_dir, svs_file)
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {svs_file}")
        logger.info(f"{'='*60}")
        
        try:
            convert_svs_to_dzi(svs_path, output_dir)
            logger.info(f"✓ Successfully converted {svs_file}")
        except Exception as e:
            logger.error(f"✗ Failed to convert {svs_file}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    logger.info(f"\n{'='*60}")
    logger.info(f"All conversions complete!")
    logger.info(f"{'='*60}")