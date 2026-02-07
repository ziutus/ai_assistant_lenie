import logging

from library.api.aws.text_detect_language_aws import detect_text_language_aws

logger = logging.getLogger(__name__)


def text_language_detect(text: str, provider: str = "aws") -> str:

    logger.info("No language selection made")

    if provider.lower() == 'aws':
        logger.info("Using AWS service to detect language")
        language = detect_text_language_aws(text=text)
    else:
        raise ValueError("Unsupported provider for text detection")

    logger.info(f"Detected language is: {language}")
    return language
