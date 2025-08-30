from library.ai import ai_ask
from library.stalker_web_document_db import StalkerWebDocumentDB
from dotenv import load_dotenv


load_dotenv()

document_id = 7476
action = "make_summary"

web_doc = StalkerWebDocumentDB(document_id=document_id)

# print(web_doc.text)
if action == "correct_text":
    prompt = f"""
    Popraw interpunkcję i składnę tekstu poniżej:

    {web_doc.text}
    """

    print(len(prompt))
    print(web_doc.text)

    result = ai_ask(query=prompt, model="Bielik-11B-v2.3-Instruct", max_token_count=200000)
    # result = ai_ask(query=prompt, model="amazon.titan-tg1-large", max_token_count=200000)

    print(result.response_text)

    # with open("tmp/bielik_test_3.txt", "w", encoding="utf-8") as f:
    #     f.write(result.response_text)

    # Ask user if they want to save the data in the database
    user_input = input("Do you want to save the response to the database? (yes/no): ").strip().lower()
    if user_input in ["yes", "y"]:
        web_doc.text = result.response_text
        web_doc.save()
        print("Poprawiony tekst zapisany w bazie danych.")

elif action == "make_summary":
    prompt = f"""
    Przygotuj podsumowanie tekstu poniżej, zwróć tylko podsumowanie:

    {web_doc.text}
    """

    print(len(prompt))
    print(web_doc.text)

    result = ai_ask(query=prompt, model="Bielik-11B-v2.3-Instruct", max_token_count=200000)
    # result = ai_ask(query=prompt, model="amazon.titan-tg1-large", max_token_count=200000)

    print(result.response_text)

    # with open("tmp/bielik_test_3.txt", "w", encoding="utf-8") as f:
    #     f.write(result.response_text)

    # Ask user if they want to save the data in the database
    user_input = input("Do you want to save the response to the database? (yes/no): ").strip().lower()
    if user_input in ["yes", "y"]:
        web_doc.summary = result.response_text
        web_doc.save()
        print("Poprawiony tekst zapisany w bazie danych.")
else:
    print(f"Nieznana akcja >{action}.")
    exit(1)


exit(0)
