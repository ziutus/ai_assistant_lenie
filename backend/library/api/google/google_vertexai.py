import vertexai
from vertexai.generative_models import GenerativeModel
import logging
import os


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def connect_to_google_llm_with_role(
    prompt: str,
    model_id: str,
    project_id: str = None,
    location: str = None
) -> str:

    if not project_id or not project_id.strip():
        project_id = os.getenv("GCP_PROJECT_ID")

    if not location or not location.strip():
        location = os.getenv("GCP_LOCATION")

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
