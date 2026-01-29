import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from google.cloud import firestore
from google.cloud import resourcemanager_v3
from dotenv import load_dotenv

load_dotenv()


# Configuration
project_id = os.environ.get("GCP_FIRESTORE_PROJECT_ID")
database = os.environ.get("GCP_FIRESTORE_DATABASE")


def get_gcp_project_info(project_id: str) -> dict:
    """Pobiera informacje o projekcie GCP, w tym organizację."""
    try:
        client = resourcemanager_v3.ProjectsClient()
        project_name = f"projects/{project_id}"
        project = client.get_project(name=project_name)

        info = {
            "project_id": project_id,
            "display_name": project.display_name,
            "organization": None,
            "folder": None
        }

        # Sprawdź czy projekt należy do organizacji
        if project.parent and project.parent.startswith("organizations/"):
            org_id = project.parent.split("/")[1]
            info["organization"] = org_id

            # Opcjonalnie: pobierz nazwę organizacji
            try:
                org_client = resourcemanager_v3.OrganizationsClient()
                org = org_client.get_organization(name=f"organizations/{org_id}")
                info["organization_name"] = org.display_name
            except Exception:
                pass

        # Sprawdź czy projekt należy do folderu
        elif project.parent and project.parent.startswith("folders/"):
            info["folder"] = project.parent.split("/")[1]

        return info
    except Exception as e:
        return {
            "project_id": project_id,
            "error": str(e)
        }


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


def convert_dynamodb_to_firestore(item: dict) -> dict:
    """Konwertuje wpis z DynamoDB do formatu Firestore."""

    # Parsuj timestamp
    created_at_str = item.get('created_at', '')
    created_at = None
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            print(f"Warning: Could not parse created_at: {created_at_str}")

    return {
        "title": item.get('title', ''),
        "url": item.get('url', ''),
        "type": item.get('type', ''),
        "language": item.get('language', ''),
        "source": item.get('source', ''),
        "created_at": created_at,
        "created_date": item.get('created_date', ''),
        "paywall": item.get('paywall', False),
        "note": item.get('note', ''),
        "chapter_list": item.get('chapter_list', ''),
        "storage_uuid": item.get('storage_uuid', ''),
        "document_id": item.get('document_id', ''),
        # Dodatkowe pola
        "tags": [],
        "read_status": "unread",
        "rating": None
    }


def migrate_articles(table_name: str = 'lenie_dev_documents') -> None:
    """Migruje artykuły z DynamoDB do Firestore."""

    if not project_id or not database:
        raise ValueError("Missing required environment variables: GCP_FIRESTORE_PROJECT_ID or GCP_FIRESTORE_DATABASE")

    # Połączenie z DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    # Połączenie z Firestore
    db = firestore.Client(project=project_id, database=database)

    # Pobierz wszystkie dokumenty z DynamoDB
    print("Pobieranie danych z DynamoDB...")
    response = table.query(
        KeyConditionExpression=Key('pk').eq('DOCUMENT'),
        ScanIndexForward=False
    )

    items = response['Items']

    # Obsługa paginacji (jeśli jest więcej niż 1MB danych)
    while 'LastEvaluatedKey' in response:
        response = table.query(
            KeyConditionExpression=Key('pk').eq('DOCUMENT'),
            ScanIndexForward=False,
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response['Items'])

    print(f"Znaleziono {len(items)} artykułów do migracji")

    # Migracja do Firestore
    batch = db.batch()
    batch_count = 0
    migrated_count = 0
    skipped_count = 0

    for item in items:
        document_id = item.get('document_id')
        if not document_id:
            print(f"Pominięto dokument bez ID: {item.get('title', 'unknown')}")
            skipped_count += 1
            continue

        # Sprawdź czy dokument już istnieje
        doc_ref = db.collection('articles').document(document_id)
        if doc_ref.get().exists:
            print(f"Dokument już istnieje: {document_id}")
            skipped_count += 1
            continue

        # Konwertuj i dodaj do batch
        firestore_data = convert_dynamodb_to_firestore(item)
        batch.set(doc_ref, firestore_data)
        batch_count += 1

        # Firestore limit: 500 operacji na batch
        if batch_count >= 500:
            batch.commit()
            migrated_count += batch_count
            print(f"Zmigrowano {migrated_count} artykułów...")
            batch = db.batch()
            batch_count = 0

    # Commit pozostałych dokumentów
    if batch_count > 0:
        batch.commit()
        migrated_count += batch_count

    print(f"\n✅ Migracja zakończona!")
    print(f"   Zmigrowano: {migrated_count} artykułów")
    print(f"   Pominięto: {skipped_count} artykułów")


def get_today_articles(db: Optional[firestore.Client] = None):
    """Artykuły z dzisiaj."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    today = datetime.now().strftime('%Y-%m-%d')

    docs = db.collection('articles')\
        .where('created_date', '==', today)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .stream()

    articles = [doc.to_dict() for doc in docs]
    print(f"Dzisiaj: {len(articles)} artykułów")
    return articles


def get_last_7_days_articles(db: Optional[firestore.Client] = None):
    """Artykuły z ostatnich 7 dni."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    date_7_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    docs = db.collection('articles')\
        .where('created_date', '>=', date_7_days_ago)\
        .order_by('created_date', direction=firestore.Query.DESCENDING)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .stream()

    articles = [doc.to_dict() for doc in docs]
    print(f"Ostatnie 7 dni: {len(articles)} artykułów")
    return articles


def get_latest_articles(limit: int = 50, db: Optional[firestore.Client] = None):
    """Ostatnie N artykułów."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    docs = db.collection('articles')\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .limit(limit)\
        .stream()

    articles = [doc.to_dict() for doc in docs]
    print(f"Ostatnie {limit} artykułów")
    return articles


def get_articles_by_source(source: str = 'own', limit: int = 100, db: Optional[firestore.Client] = None):
    """Artykuły z określonego źródła."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    docs = db.collection('articles')\
        .where('source', '==', source)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .limit(limit)\
        .stream()

    return [doc.to_dict() for doc in docs]


def get_paywall_articles(db: Optional[firestore.Client] = None):
    """Artykuły za paywallem."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    docs = db.collection('articles')\
        .where('paywall', '==', True)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .stream()

    return [doc.to_dict() for doc in docs]


class FirestoreCostMonitor:
    """Monitoruje koszty operacji Firestore."""

    def __init__(self):
        self.reads = 0
        self.writes = 0
        self.deletes = 0

    def track_query(self, query_result):
        """Śledzi liczbę odczytów w zapytaniu."""
        count = len(list(query_result))
        self.reads += count
        return count

    def track_write(self):
        """Śledzi zapis."""
        self.writes += 1

    def track_delete(self):
        """Śledzi usunięcie."""
        self.deletes += 1

    def get_costs(self):
        """Oblicza szacunkowe koszty."""
        # Ceny po przekroczeniu free tier
        read_cost = max(0, self.reads - 50000) * 0.06 / 100000
        write_cost = max(0, self.writes - 20000) * 0.18 / 100000
        delete_cost = max(0, self.deletes - 20000) * 0.02 / 100000

        total = read_cost + write_cost + delete_cost

        return {
            "reads": self.reads,
            "writes": self.writes,
            "deletes": self.deletes,
            "read_cost_usd": round(read_cost, 4),
            "write_cost_usd": round(write_cost, 4),
            "delete_cost_usd": round(delete_cost, 4),
            "total_cost_usd": round(total, 4),
            "total_cost_pln": round(total * 4, 2)  # ~4 PLN/USD
        }

    def print_report(self):
        """Wyświetla raport kosztów."""
        costs = self.get_costs()
        print("\n" + "="*50)
        print("📊 RAPORT KOSZTÓW FIRESTORE")
        print("="*50)
        print(f"Odczyty:     {costs['reads']:,} (darmowe: 50,000/dzień)")
        print(f"Zapisy:      {costs['writes']:,} (darmowe: 20,000/dzień)")
        print(f"Usunięcia:   {costs['deletes']:,} (darmowe: 20,000/dzień)")
        print("-"*50)
        print(f"Koszt odczytów:   ${costs['read_cost_usd']}")
        print(f"Koszt zapisów:    ${costs['write_cost_usd']}")
        print(f"Koszt usunięć:    ${costs['delete_cost_usd']}")
        print("-"*50)
        print(f"💰 RAZEM:         ${costs['total_cost_usd']} (~{costs['total_cost_pln']} PLN)")
        print("="*50 + "\n")


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


def migrate_s3_uuid_to_storage_uuid(db: Optional[firestore.Client] = None, dry_run: bool = True):
    """Zamienia pole s3_uuid na storage_uuid w istniejących artykułach."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    print("Pobieranie artykułów z Firestore...")
    docs = db.collection('articles').stream()

    batch = db.batch()
    batch_count = 0
    updated_count = 0
    total_count = 0

    for doc in docs:
        total_count += 1
        doc_data = doc.to_dict()

        # Sprawdź czy dokument ma pole s3_uuid
        if 's3_uuid' in doc_data:
            s3_uuid_value = doc_data['s3_uuid']

            if dry_run:
                print(f"[DRY RUN] Zamieniono by s3_uuid na storage_uuid w dokumencie: {doc.id} (wartość: {s3_uuid_value})")
            else:
                # Usuń stare pole i dodaj nowe
                update_data = {
                    's3_uuid': firestore.DELETE_FIELD,
                    'storage_uuid': s3_uuid_value
                }
                batch.update(doc.reference, update_data)
                batch_count += 1
                updated_count += 1

                # Firestore limit: 500 operacji na batch
                if batch_count >= 500:
                    batch.commit()
                    print(f"Zaktualizowano {updated_count} artykułów...")
                    batch = db.batch()
                    batch_count = 0

    # Commit pozostałych dokumentów
    if batch_count > 0 and not dry_run:
        batch.commit()

    print(f"\n✅ Operacja zakończona!")
    print(f"   Sprawdzono: {total_count} artykułów")
    print(f"   {'Zostałoby zaktualizowanych' if dry_run else 'Zaktualizowano'}: {updated_count} artykułów")
    if dry_run:
        print(f"\n⚠️  To był tryb TEST (dry_run=True). Aby faktycznie zmienić pola, uruchom z dry_run=False")

    return updated_count


def clean_empty_fields(db: Optional[firestore.Client] = None, dry_run: bool = True):
    """Usuwa puste pola chapter_list i tags z istniejących artykułów."""
    if db is None:
        if not project_id or not database:
            raise ValueError("Missing required environment variables")
        db = firestore.Client(project=project_id, database=database)

    # Pobierz wszystkie artykuły
    print("Pobieranie artykułów z Firestore...")
    docs = db.collection('articles').stream()

    batch = db.batch()
    batch_count = 0
    updated_count = 0
    total_count = 0

    for doc in docs:
        total_count += 1
        doc_data = doc.to_dict()
        fields_to_delete = []

        # Sprawdź chapter_list
        chapter_list = doc_data.get('chapter_list', None)
        if chapter_list is not None and (chapter_list == '' or chapter_list == [] or chapter_list == {}):
            fields_to_delete.append('chapter_list')

        # Sprawdź tags
        tags = doc_data.get('tags', None)
        if tags is not None and (tags == '' or tags == [] or tags == {}):
            fields_to_delete.append('tags')

        # Jeśli są pola do usunięcia
        if fields_to_delete:
            if dry_run:
                print(f"[DRY RUN] Usunięto by pola {fields_to_delete} z dokumentu: {doc.id}")
            else:
                # Użyj FieldPath.delete() do usunięcia pól
                update_data = {field: firestore.DELETE_FIELD for field in fields_to_delete}
                batch.update(doc.reference, update_data)
                batch_count += 1
                updated_count += 1

                # Firestore limit: 500 operacji na batch
                if batch_count >= 500:
                    batch.commit()
                    print(f"Zaktualizowano {updated_count} artykułów...")
                    batch = db.batch()
                    batch_count = 0

    # Commit pozostałych dokumentów
    if batch_count > 0 and not dry_run:
        batch.commit()

    print(f"\n✅ Operacja zakończona!")
    print(f"   Sprawdzono: {total_count} artykułów")
    print(f"   {'Zostałoby zaktualizowanych' if dry_run else 'Zaktualizowano'}: {updated_count} artykułów")
    if dry_run:
        print(f"\n⚠️  To był tryb TEST (dry_run=True). Aby faktycznie usunąć pola, uruchom z dry_run=False")

    return updated_count


def print_gcp_connection_info():
    """Wyświetla informacje o połączeniu z Google Cloud."""
    print("=" * 60)
    print("🔐 POŁĄCZENIE Z GOOGLE CLOUD")
    print("=" * 60)

    if project_id:
        gcp_info = get_gcp_project_info(project_id)
        if "error" in gcp_info:
            print(f"⚠️  Nie można pobrać informacji o projekcie: {gcp_info['error']}")
            print(f"Project ID:   {project_id}")
        else:
            if gcp_info.get("organization_name"):
                print(f"Organization: {gcp_info['organization_name']} (ID: {gcp_info['organization']})")
            elif gcp_info.get("organization"):
                print(f"Organization: {gcp_info['organization']}")

            if gcp_info.get("display_name"):
                print(f"Project:      {gcp_info['display_name']}")
            print(f"Project ID:   {gcp_info['project_id']}")

            if gcp_info.get("folder"):
                print(f"Folder ID:    {gcp_info['folder']}")
    else:
        print("⚠️  Brak GCP_FIRESTORE_PROJECT_ID")

    print(f"Database:     {database}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    # Wyświetl informacje o połączeniu GCloud (opcjonalnie)
    # print_gcp_connection_info()

    # Przykłady użycia:

    # 1. Migracja artykułów z DynamoDB do Firestore
    migrate_articles()

    # 2. Migracja s3_uuid -> storage_uuid
    # Najpierw uruchom w trybie test (dry_run=True)
    # migrate_s3_uuid_to_storage_uuid(dry_run=True)
    # Po sprawdzeniu wyników uruchom faktyczną migrację (dry_run=False)
    # migrate_s3_uuid_to_storage_uuid(dry_run=False)

    # 3. Czyszczenie pustych pól
    # Najpierw uruchom w trybie test (dry_run=True)
    # clean_empty_fields(dry_run=True)
    # Po sprawdzeniu wyników uruchom faktyczne usuwanie (dry_run=False)
    # clean_empty_fields(dry_run=False)

    # 4. Zapytania o artykuły
    # get_today_articles()
    # get_last_7_days_articles()
    # get_latest_articles(limit=10)

    # 5. Monitorowanie kosztów
    # db = firestore.Client(project=project_id, database=database)
    # monitor = FirestoreCostMonitor()
    # docs = db.collection('articles').limit(10).stream()
    # monitor.track_query(docs)
    # monitor.print_report()

    # 6. Storytel (oryginalna funkcjonalność)
    main_storytel()
