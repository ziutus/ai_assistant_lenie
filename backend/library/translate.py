import os
import logging

from library.api.aws.text_translate_aws import translate_aws
from library.translateResult import TranslateResult
from library.stalker_cache import cache_get, cache_write

logger = logging.getLogger(__name__)


def text_translate(text: str, target_language: str, source_language: str = "pl", model: str = "aws_translate") \
        -> TranslateResult:
    use_cache = os.getenv("USE_CACHE")
    cache_status = None

    if use_cache and target_language == "en":
        logging.info("Using cache to find translation to English")
        cache_status = cache_get('translation', text)

    if cache_status:
        logger.info(f"Translation found in cache: {cache_status}")
        result = TranslateResult(text=text, target_language=target_language,
                                 source_language=source_language, translated_text=cache_status, cached=True)
        return result

    if model == "aws_translate":
        logger.info("will use AWS service to translate query to English")
        result = translate_aws(text=text, target_language=target_language, source_language=source_language)
        logger.info(f"Translated query to English is:{result.translated_text}")

        if use_cache and target_language == "en":
            cache_write('translation', key=text, data=result.translated_text, provider='aws')
        return result
    else:
        raise Exception("Wrong translate model: >{model}")
