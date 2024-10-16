import library.api.aws.dynamodb_cache_language_check
import library.api.aws.dynamodb_cache_ai_query
import library.api.aws.dynamodb_cache_translation

from library.text_functions import get_hash


def cache_get(cache_name: str, string: str, provider: str = 'aws') -> bool|str:
    string_hash = get_hash(string)

    if cache_name == "language":
        response = library.api.aws.dynamodb_cache_language_check.cache_get_language(string_hash, provider)
        if response:
            return response['response']['S']
        else:
            return False
    elif cache_name == "translation":
        response = library.api.aws.dynamodb_cache_translation.cache_get_translation(string_hash, provider)
        if response:
            return response['response']['S']
        else:
            return False
    elif cache_name == "query":
        response = library.api.aws.dynamodb_cache_ai_query.cache_get_query(string_hash, provider)
        if response:
            return response['response']['S']
        else:
            return False
    else:
        raise Exception("Missing cache_name")


def cache_write(cache_name: str, key: str, data: str, provider: str) -> None:
    if cache_name == "language":
        library.api.aws.dynamodb_cache_language_check.cache_write_language_check(key, data, provider)
    elif cache_name == "translation":
        library.api.aws.dynamodb_cache_translation.cache_write_translation(key, data, provider)
    elif cache_name == "query":
        library.api.aws.dynamodb_cache_ai_query.cache_write_query(key, data, provider)
    else:
        raise Exception("Missing cache_name")
    return None
