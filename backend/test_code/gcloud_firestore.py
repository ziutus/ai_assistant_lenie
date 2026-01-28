import json
import os
from pathlib import Path

from google.cloud import firestore
from dotenv import load_dotenv
load_dotenv()

def _build_storytel_doc_data(payload: dict) -> dict:
    return {
        "title": payload.get("name"),
        "author": payload.get("author"),
        "cover_image": payload.get("image"),
        "language": payload.get("inLanguage"),
        "isbn": payload.get("isbn"),
        "date_published": payload.get("datePublished"),
        "description": payload.get("description"),
        "my_rating": None,
        "my_rank": None,
        "source": "storytel"
    }




project_id = os.environ.get("GCP_FIRESTORE_PROJECT_ID")
database = os.environ.get("GCP_FIRESTORE_DATABASE")

def main_storytel() -> None:
    if not project_id or not database:
        raise ValueError("Missing required environment variables: GCP_FIRESTORE_PROJECT_ID or GCP_FIRESTORE_DATABASE")

    db = firestore.Client(project=project_id, database=database)
    base_dir = Path(__file__).resolve().parent / "tmp"
    json_files = sorted(base_dir.glob("storytel_*.json"))

    if not json_files:
        print("No storytel_*.json files found.")
        return

    for json_path in json_files:
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        title = payload.get("name")
        if not title:
            print(f"Skipping {json_path.name}: missing 'name'.")
            continue

        doc_ref = db.collection("audiobooks").document(title)
        snapshot = doc_ref.get()

        if snapshot.exists:
            print(f"Skip existing: {title}")
            continue

        data_payload = _build_storytel_doc_data(payload)
        doc_ref.set(data_payload)
        print(f"Added: {title}")


if __name__ == "__main__":
    main_storytel()
