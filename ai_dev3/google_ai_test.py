import logging
import os
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def connect_to_google_llm_with_role(
        project_id: str,
        location: str,
        prompt: str,
        model_id: str
) -> str:
    """
    Connects to Google LLM model (Vertex AI) using Application Default Credentials
    (based on IAM role) and returns a response.

    Args:
      project_id: ID of your Google Cloud project.
      location: Region where Vertex AI operates, e.g. "us-central1" or "europe-central2".
      prompt: Query you want to send to the model.
      model_id: Model ID to use (default "gemini-2.0-flash-lite-001").

    Returns:
      Text response from the LLM model.

    Raises:
      ValueError: If parameters are empty or invalid.
      Exception: If an error occurs during communication with Vertex AI.

    Example:
      >>> response = connect_to_google_llm_with_role(
      ...     project_id="my-project-id",
      ...     location="europe-central2",
      ...     prompt="What is AI?"
      ... )
      >>> print(response)
    """
    # Validate parameters
    if not project_id or not project_id.strip():
        raise ValueError("project_id cannot be empty")
    if not location or not location.strip():
        raise ValueError("location cannot be empty")
    if not prompt or not prompt.strip():
        raise ValueError("prompt cannot be empty")
    if not model_id or not model_id.strip():
        raise ValueError("model_id cannot be empty")

    try:
        logger.info(f"Initializing Vertex AI for project {project_id} in region {location}")

        # Initialize Vertex AI in the specified project and region.
        # The library will automatically find authentication credentials (ADC).
        vertexai.init(project=project_id, location=location)

        logger.info(f"Creating model instance {model_id}")
        model = GenerativeModel(model_id)

        logger.info("Sending prompt to model")
        response = model.generate_content(prompt)

        # Validate response
        if not response or not hasattr(response, 'text') or not response.text:
            logger.error("Model returned empty response")
            raise ValueError("Model returned empty response")

        logger.info("Received response from model")
        return response.text

    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Error during communication with Vertex AI: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # --- Usage example ---
    # Make sure you are authenticated (e.g., via `gcloud auth application-default login`)
    # or that the code runs in a GCP environment with a properly configured service account.

    # Get data from environment variables or use default values
    gcp_project_id = os.getenv("GCP_PROJECT_ID")
    gcp_location = os.getenv("GCP_LOCATION", "europe-central2")
    user_prompt = "Describe in three sentences what Vertex AI is."

    try:
        model_response = connect_to_google_llm_with_role(
            project_id=gcp_project_id,
            location=gcp_location,
            prompt=user_prompt,
            model_id="gemini-2.0-flash-lite-001"
        )

        print("\nResponse from model:")
        print(model_response)
    except Exception as e:
        logger.error(f"Failed to get response: {e}")
        print(f"\nError: {e}")
