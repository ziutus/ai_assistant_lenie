import os

import psycopg2
from psycopg2 import sql


class StalkerCacheEmbeddings:
    def __init__(self):
        # if os.getenv("DEBUG"):
        #     print("Connecting to PostgreSQL database...")
        #     print("POSTGRESQL_HOST: " + os.getenv("POSTGRESQL_HOST"))
        #     print("POSTGRESQL_DATABASE: " + os.getenv("POSTGRESQL_DATABASE"))
        #     print("POSTGRESQL_USER: " + os.getenv("POSTGRESQL_USER"))
        #     print("POSTGRESQL_PASSWORD: " + os.getenv("POSTGRESQL_PASSWORD"))
        #     print("POSTGRESQL_PORT: " + os.getenv("POSTGRESQL_PORT"))

        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRESQL_HOST"),
            database=os.getenv("POSTGRESQL_DATABASE"),
            user=os.getenv("POSTGRESQL_USER"),
            password=os.getenv("POSTGRESQL_PASSWORD"),
            port=os.getenv("POSTGRESQL_PORT")
        )

    def embedding_cache_exist(self, text_hash):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT embedding FROM public.embeddings_cache WHERE text_hash = %s", (text_hash, )
        )
        embedding_data = cursor.fetchone()

        if embedding_data is None:
            return None
        else:
            response = {
                "status": "success",
                "embedding": embedding_data[0]
            }
            return response

    def embedding_cache_delete(self, emb_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM public.embeddings_cache WHERE id = %s", (emb_id, ))
        self.conn.commit()

    def embedding_cache_add(self, embedding, text, text_hash, model):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO public.embeddings_cache(model, text, embedding, text_hash) "
            "VALUES (%s,%s, %s, %s)",
            (model, text, embedding, text_hash)
        )
        self.conn.commit()