import os
from pprint import pprint
from dotenv import load_dotenv
import argparse
import logging

import library.embedding as embedding
from library.ai import ai_ask, ai_model_need_translation_to_english
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.text_detect_language import text_language_detect
from library.stalker_cache import cache_get, cache_write

load_dotenv()
logging.basicConfig(level=logging.INFO)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Accepts a question from CLI")
    parser.add_argument('--minimal_similarity', type=float, default="0.30",
                        help="Set minimal similarity threshold", required=False)
    parser.add_argument('--question', type=str, help="Enter your question", required=False)
    parser.add_argument("-query", help="Specify the question to ask LLM")
    parser.add_argument("-model", help="model to query", default="amazon.titan-tg1-large")
    # parser.add_argument("-model", help="model to query", default="gpt-4")
    parser.add_argument("-nc", action="store_true", help="Never use cache")
    parser.add_argument("-en", action="store_true", help="The text string is in English")
    parser.add_argument("-pl", action="store_true", help="The text string is in Polish (default language)")

    args = parser.parse_args()
    llm_model = args.model
    language_default = "pl"
    # use_cache = os.getenv("USE_CACHE")
    use_cache = False
    answer = True
    use_own_knowledge = True
    model_embedding = "amazon.titan-embed-text-v1"
    # model = "text-embedding-ada-002"
    knowledge_database_txt = ""
    similar_results = None

    if args.question:
        question = args.question
    else:
        # question = "jakie narzędzia wspomagają pracę z Kubernetesem?"
        # question = "Kubernetes i security"
        # question = "Jak zrobić animację 3D w przeglądarce?"
        # question = "Jakie narzędzia wspomagają pracę w konsoli linuksowej?"
        question = "Czy są sprawy sądowe związane z filmami porno stworzonymi przez AI?"
        # question = "Czy są egzaminy z języka Python?"
        # question = "mapa trendów"
        # question = "Wymień osoby zajmujące się geopolityką"
        # question = "Jakie zakłady produkują rakiety przeciwlotnicze w Rosji"
        # question = "Jakich dronów używa polska armia?"
        # question = "Jaki system radarowy atakują ukraincy w rosji?"
        # question = "Czym jest SLO w pracy DevOps-a?"
        # question = "Co to jest deepfake?"
        # question = "Jak Rosja straszy sąsiadów?"
        # question = "What is the best way to validate if python flask application is alive on AWS Fragate? I'm using ECS service and want to define Healthcheck"

    language = language_default
    if args.nc:
        use_cache = False
        os.environ['USE_CACHE'] = 'False'

    if args.en:
        logging.info("Your text is supposed to be in English.")
        language = "en"
    elif args.pl:
        logging.info("Your text is supposed to be in Polish")
        language = "pl"
    else:
        logging.info("No language selection made, checking using AWS service")
        language = text_language_detect(text=question)

    logging.info(f"Language: {language}")
    query = question

    if answer and use_cache:
        answer_cached = cache_get('query', query, llm_model)
        if answer_cached:
            logging.info("Entry found in cache")
            print(answer_cached)
            exit(0)

    if use_own_knowledge:
        question_embedding = embedding.get_embedding(model=model_embedding, text=query)

        if question_embedding.status == "error" or question_embedding.embedding is None:
            logging.error("question embedding not found (None), please check your input")
            exit(1)

        # pprint(question_embedding)
        websites = WebsitesDBPostgreSQL()

        similar_results = websites.get_similar(model=model_embedding, embedding=question_embedding.embedding, limit=30,
                                               minimal_similarity=args.minimal_similarity)

        logging.info(f"Minimal similarity: {args.minimal_similarity}")

        embedding_text_length = 0
        if similar_results is None:
            logging.error("Similar results not found (None), looks like embedding service is not available")
            exit(1)

        websites_in_result = []
        for result in similar_results:
            embedding_text_length += result['embeddings_text_length']
            if result['website_id'] not in websites_in_result:
                websites_in_result.append(result['website_id'])
            print(f"{result['website_id']} {result['id']} {result['similarity']} {result['url']}")
            print(result["title"])
            if ai_model_need_translation_to_english(llm_model):
                print(result["text"])
                knowledge_database_txt += "\n---\n" + result["text"]
            else:
                print(result["text_original"])
                knowledge_database_txt += "\n---\n" + result["text_original"]

            print("\n")
        print("\nSummary:")
        print(f"Length of embedded text: {embedding_text_length}")
        print(f"Websites in DB with those embeddings: {len(websites_in_result)}")
        pprint(websites_in_result.sort())

        print(f"Created local database for this query (len: {len(knowledge_database_txt)} characters):")
        print(knowledge_database_txt)

    if answer:
        if use_own_knowledge:
            query = f"""
            answer question: {query}
            using below knowledge base:
            {knowledge_database_txt}
            """

        logging.debug(f"Will ask {llm_model} query: {query}")
        print(f"Query: {query}")
        answer_en = ai_ask(query=query, model=llm_model).response_text

        pprint(answer_en)

        # print(f"Answer: {answer_en}")

        if use_cache:
            cache_write('query', query, answer_en, llm_model)

        if use_own_knowledge:
            print("\nSources:")
            sources_printed = []
            i = 1
            for source in similar_results:
                if source["website_id"] not in sources_printed:
                    sources_printed.append(source["website_id"])
                    print(i, source['document_type'], source["website_id"], source['title'] + " " + source["url"])
                    i += 1
