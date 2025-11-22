from dotenv import load_dotenv

from library.ai import ai_ask

load_dotenv()

if __name__ == "__main__":
    user_prompt = "Describe in one sentence what Vertex AI is."
    model_id = "gemini-2.0-flash-lite-001"

    try:
        response = ai_ask(user_prompt, model_id)
        print(f"\nResponse from model: {response.response_text}")
    except Exception as e:
        print(f"\nError: {e}")
