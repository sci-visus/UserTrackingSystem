import openslide
import json
import os
import glob

# Base directory where your .svs subdirectories live
SVS_DIR = "/local/data/magicscan/HnE/TCGA-BRCA/tissue_slides/primary_tumor"

# Base directory where you want to save metadata, mirroring SVS_DIR structure
OUT_DIR = "/local/data/magicscan/dzi_ink_datasets/HnE/TCGA-BRCA/tissue_slides/primary_tumor"

os.makedirs(OUT_DIR, exist_ok=True)

def read_svs_metadata(svs_path):
    slide = openslide.OpenSlide(svs_path)

    meta = {
        "filename": os.path.basename(svs_path),
        "full_path": svs_path,
        "dimensions": {
            "width": slide.dimensions[0],
            "height": slide.dimensions[1],
        },
        "level_count": slide.level_count,
        "level_dimensions": [
            {"width": w, "height": h} for (w, h) in slide.level_dimensions
        ],
        "level_downsamples": list(slide.level_downsamples),
        "associated_images": list(slide.associated_images.keys()),
        # Convenience fields:
        "mpp_x": slide.properties.get(openslide.PROPERTY_NAME_MPP_X),
        "mpp_y": slide.properties.get(openslide.PROPERTY_NAME_MPP_Y),
        "objective_power": slide.properties.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER),
        "vendor": slide.properties.get(openslide.PROPERTY_NAME_VENDOR),
    }

    slide.close()
    return meta

def main():
    found_any = False

    # Walk through all subdirectories of SVS_DIR
    for root, dirs, files in os.walk(SVS_DIR):
        # Collect .svs files in this directory
        svs_files = [f for f in files if f.lower().endswith(".svs")]
        if not svs_files:
            continue  # nothing to do in this folder

        found_any = True

        # Compute relative path from SVS_DIR to current folder
        rel_dir = os.path.relpath(root, SVS_DIR)

        # Mirror that structure under OUT_DIR
        out_dir_for_root = os.path.join(OUT_DIR, rel_dir)
        os.makedirs(out_dir_for_root, exist_ok=True)

        for svs_file in svs_files:
            svs_path = os.path.join(root, svs_file)
            base = os.path.splitext(svs_file)[0]

            out_path = os.path.join(
                out_dir_for_root,
                f"{base}_svs_scalebar_metadata.json"
            )

            print(f"Reading metadata for {svs_path} -> {out_path}")
            meta = read_svs_metadata(svs_path)

            with open(out_path, "w") as f:
                json.dump(meta, f, indent=2)

            # Optional permissions
            os.chmod(out_path, 0o666)

    if not found_any:
        print(f"No .svs files found under {SVS_DIR}")

if __name__ == "__main__":
    main()
