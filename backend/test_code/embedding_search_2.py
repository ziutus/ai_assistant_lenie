import os
from pprint import pprint
from dotenv import load_dotenv
import library.embedding as embedding
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

load_dotenv()

# query = "Jakie plany wobec Grenlandii ma Trump"
# query = "Jakie działania podejmuje Rosja na morzach europejskich"
# query = "Gzie w Europie znajdują się złoża litu?"
query = "Jakie problemy ma USA?"

model_embedding = os.getenv("EMBEDDING_MODEL")
print(f"I'm searching using embedding model >{model_embedding}")
question_embedding = embedding.get_embedding(model=model_embedding, text=query)

# if not question_embedding.status:
#     print("Problem with embedding, exiting")
#     exit(1)

emb = question_embedding.embedding

websites = WebsitesDBPostgreSQL()
similar_results = websites.get_similar(model=model_embedding, embedding=emb, limit=30,
                                       minimal_similarity=0.30)

pprint(similar_results)
