import os
import logging

from library.api.aws.text_detect_language_aws import detect_text_language_aws
from library.stalker_cache import cache_get, cache_write

logger = logging.getLogger(__name__)


def text_language_detect(text: str, provider: str = "aws") -> str:
    use_cache = os.getenv("USE_CACHE")
    cache_status = None

    logger.info("No language selection made")
    if use_cache:
        cache_status = cache_get('language', text)

    if use_cache and cache_status:
        logger.info("Language found in cache")
        logger.info(cache_status)
        language = cache_status
    else:

        if provider.lower() == 'aws':
            logger.info("Using AWS service to detect language")
            language = detect_text_language_aws(text=text)
        else:
            raise ValueError("Unsupported provider for text detection")

        if use_cache:
            cache_write('language', key=text, data=language, provider='aws')

    logger.info(f"Detected language is: {language}")
    return language
