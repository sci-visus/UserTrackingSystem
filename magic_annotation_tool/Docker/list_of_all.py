from pymongo import MongoClient
import json

# --- Config ---
MONGO_URL = "mongodb+srv://scrgiorgio:J30uQ1aHHPecsjce@cluster0.rduj1ya.mongodb.net/magicscan_ink?retryWrites=true&w=majority&maxPoolSize=5&minPoolSize=1&maxIdleTimeMS=10000&waitQueueTimeoutMS=2000&serverSelectionTimeoutMS=10000&connectTimeoutMS=10000&socketTimeoutMS=30000&heartbeatFrequencyMS=10000&tlsAllowInvalidCertificates=true&tlsAllowInvalidHostnames=true"
DATABASE_NAME = "magicscan_ink_dzi"

client = MongoClient(MONGO_URL)
db = client[DATABASE_NAME]

entries = []
entry_number = 1

# Loop through all collections
for coll_name in db.list_collection_names():
    collection = db[coll_name]

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
            "collection_name": coll_name
        }

        entries.append(entry)
        entry_number += 1

print(f"Total entries collected: {len(entries)}")

# --- Split into 4 JSON files, 247 entries each (without changing entry_number) ---
CHUNK_SIZE = 274
NUM_JSONS = 12

for i in range(NUM_JSONS):
    start = i * CHUNK_SIZE
    end = start + CHUNK_SIZE
    chunk = entries[start:end]

    output_json = f"tiles_directory_list_part_{i+1}.json"
    with open(output_json, "w") as f:
        json.dump(chunk, f, indent=2)

    print(f"Saved {len(chunk)} entries to {output_json}")
