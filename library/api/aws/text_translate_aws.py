import logging
import os
import boto3
from aws_xray_sdk.core import xray_recorder, patch_all
from library.translateResult import TranslateResult

patch_all()
logger = logging.getLogger(__name__)


def translate_aws(text: str, target_language: str, source_language: str = "pl") -> TranslateResult:

    result = TranslateResult(text=text, target_language=target_language, source_language=source_language)

    try:
        boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))

        # sts_client = boto_session.client('sts')
        # response = sts_client.get_caller_identity()
        # print(response)

        client = boto_session.client('translate')

        # https://docs.aws.amazon.com/translate/latest/APIReference/API_TranslateText.html
        logger.info(f"text len: {len(text)}, in bytes: {len(text.encode('utf-8'))}")
        if len(text.encode('utf-8')) < 10000:
            with xray_recorder.in_subsegment('translate single test') as subsegment:
                response = client.translate_text(
                    Text=text,
                    SourceLanguageCode=source_language,
                    TargetLanguageCode=target_language
                )
                result.translated_text = response['TranslatedText']

                subsegment.put_metadata('response', response)
                return result
        else:
            rows = text.split("\n\n")
            rows_english = []
            i = 1
            rows_nb = len(rows)
            for row in rows:
                logging.info(f"row len: {len(row)}")
                if len(row.encode('utf-8')) > 10000:
                    result.error_message = "Even split text is too long"
                    result.status = "error"
                    return result

                if (len(row)) == 0:
                    continue

                with xray_recorder.in_subsegment(f'translate part {i} from {rows_nb}') as subsegment:
                    response = client.translate_text(
                        Text=row,
                        SourceLanguageCode=source_language,
                        TargetLanguageCode=target_language
                    )
                    rows_english.append(response['TranslatedText'])
                    subsegment.put_metadata('response', response)

                i += 1

            result.translated_text = '\n\n'.join(rows_english)
            return result

    except Exception as e:
        result.error_message = str(e)
        result.status = "error"
        return result
