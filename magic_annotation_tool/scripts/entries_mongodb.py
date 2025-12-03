from pymongo import MongoClient
import json

# --- Config ---
MONGO_URL = MONGO_URL
DATABASE_NAME = DATABASE_NAME

client = MongoClient(MONGO_URL)
db = client[DATABASE_NAME]

entries = []
entry_number = 1

collection = db["BACH-Challenge"]

# Only docs that have tiles_directory
cursor = collection.find(
    {"tiles_directory": {"$exists": True}},
    {"tiles_directory": 1, "svs_file": 1, "filename": 1}  # projection
)

for doc in cursor:
    # Try a few common field names for the svs file
    svs_file = (
        doc.get("svs_file") or
        doc.get("filename") or
        doc.get("svs") or
        doc.get("slide_name") or
        "UNKNOWN"
    )

    entry = {
        "entry_number": entry_number,
        "svs_file": svs_file,
        "tiles_directory": doc.get("tiles_directory"),
        "collection_name": collection.name
    }

    entries.append(entry)
    entry_number += 1

print(f"Total entries collected: {len(entries)}")

# --- Split into 4 JSON files, 247 entries each (without changing entry_number) ---
CHUNK_SIZE = 30
NUM_JSONS = 1

for i in range(NUM_JSONS):
    start = i * CHUNK_SIZE
    end = start + CHUNK_SIZE
    chunk = entries[start:end]

    output_json = f"tiles_directory_list_bach_{i+1}.json"
    with open(output_json, "w") as f:
        json.dump(chunk, f, indent=2)

    print(f"Saved {len(chunk)} entries to {output_json}")
