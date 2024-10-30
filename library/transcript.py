from library.api.aws.transcript import aws_transcript
import math

transcript_prices_by_minute = {
    'AWS': 0.02400,
    'OpenAI': 0.006,  # https://openai.com/api/pricing/
    'assemblyai': 0.002  # https://www.assemblyai.com/pricing
}


def transcript(transcript_file_local: str, media_format: str, language_code: str = None,
               transcript_file_remote: str = None,
               s3_bucket=None, provider: str = 'aws'):
    if provider == 'local':
        print(f"functionality to analyze local file: {transcript_file_local} should be implemented")
        return None

    if provider == 'aws':
        return aws_transcript(s3_bucket=s3_bucket, s3_key=transcript_file_remote, language_code=language_code,
                              media_format=media_format)

    return None


def transcript_price(length_sec: int) -> dict[str, float]:
    length_min = math.ceil(length_sec / 60)
    result = {}
    for provider in transcript_prices_by_minute:
        result[provider] = round(round(length_min) * transcript_prices_by_minute[provider], 2)

    return result
