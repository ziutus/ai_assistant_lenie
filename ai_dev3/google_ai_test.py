from dotenv import load_dotenv

import library.api.google.google_vertexai as google_vertexai

load_dotenv()

if __name__ == "__main__":
    user_prompt = "Describe in one sentence what Vertex AI is."
    model_id = "gemini-2.0-flash-lite-001"

    try:
        model_response = google_vertexai.connect_to_google_llm_with_role(
            prompt=user_prompt,
            model_id=model_id
        )

        print(f"\nResponse from model: {model_response}")
    except Exception as e:
        print(f"\nError: {e}")
