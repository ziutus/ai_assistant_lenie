import os

import boto3


def aws_transcript(s3_bucket: str, s3_key: str, media_format: str, language_code: str | None = None,
                   multi_language: bool = False) -> dict[str, str]:
    job_name = s3_key
    transcript_job_needed = True

    # MediaFormat='mp3'|'mp4'|'wav'|'flac'|'ogg'|'amr'|'webm'|'m4a',
    if media_format == 'audio/wav':
        media_format = "vaw"
    elif media_format == 'video/mp4':
        media_format = "mp4"

    boto_session = boto3.session.Session(region_name=os.getenv("AWS_REGION"))
    transcript_client = boto_session.client(service_name='transcribe', region_name=os.getenv("AWS_REGION"))

    response = transcript_client.list_transcription_jobs(
        JobNameContains=job_name
    )

    for transcript_job in response['TranscriptionJobSummaries']:
        print(transcript_job["TranscriptionJobStatus"])
        if transcript_job["TranscriptionJobName"] == job_name and transcript_job["TranscriptionJobStatus"] in ["COMPLETED", "IN_PROGRESS"]: # noqa
            transcript_job_needed = False

    uri_media_file = "s3://" + s3_bucket + "/" + job_name
    if transcript_job_needed:
        if not language_code:
            if multi_language:
                transcript_client.start_transcription_job(
                    TranscriptionJobName=job_name,
                    Media={'MediaFileUri': uri_media_file},
                    MediaFormat=media_format,
                    IdentifyMultipleLanguages=True
                )
            else:
                transcript_client.start_transcription_job(
                    TranscriptionJobName=job_name,
                    Media={'MediaFileUri': uri_media_file},
                    MediaFormat=media_format,
                    IdentifyLanguage=True
                )
        else:
            transcript_client.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={'MediaFileUri': uri_media_file},
                MediaFormat=media_format,
                LanguageCode=language_code
            )

    response = transcript_client.get_transcription_job(
        TranscriptionJobName=job_name
    )
    if response['TranscriptionJob']['TranscriptionJobStatus'] == "COMPLETED":
        remote_file = response['TranscriptionJob']['Transcript']['TranscriptFileUri']
        return {
            "status": "success",
            "remote_file": remote_file
        }
    else:
        return {
            "status": response['TranscriptionJob']['TranscriptionJobStatus']
        }
