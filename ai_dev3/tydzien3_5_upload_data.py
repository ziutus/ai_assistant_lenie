from neo4j import GraphDatabase
import csv
from pprint import pprint

# Połączenie z Neo4j
uri = "neo4j://localhost:7687"
username = "neo4j"
password = "password"  # Zmień na swoje hasło Neo4j
driver = GraphDatabase.driver(uri, auth=(username, password))


# Funkcja do załadowania użytkowników z users.csv
def load_users(file_path):
    with driver.session() as session:
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                pprint(row)
                query = """
                CREATE (:User {user_id: $id, username: $username, access_level: $access_level, is_active: $is_active, lastlog: $lastlog})
                """
                session.run(query, {
                    "id": int(row['id']),
                    "username": row['username'],
                    "access_level": row['access_level'],
                    "is_active": int(row['is_active']),
                    "lastlog": row['lastlog']
                })


# Funkcja do załadowania połączeń z connections.csv
def load_connections(file_path):
    with driver.session() as session:
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                pprint(row)
                query = """
                MATCH (u1:User {user_id: $user1_id}), (u2:User {user_id: $user2_id})
                CREATE (u1)-[:KNOWS]->(u2)
                """
                session.run(query, {
                    "user1_id": int(row['user1_id']),
                    "user2_id": int(row['user2_id'])
                })


# Ścieżki do plików CSV
users_csv_path = "tmp/users.csv"  # Zamień na swoją rzeczywistą ścieżkę
connections_csv_path = "tmp/connections.csv"  # Zamień na swoją rzeczywistą ścieżkę

# Wczytywanie danych
# load_users(users_csv_path)
load_connections(connections_csv_path)

driver.close()