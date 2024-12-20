import os

import assemblyai as aai


def transcript_assemblyai(audio_local_file, language_code="en"):
    aai.settings.api_key = os.getenv("ASSEMBLYAI")

    config = aai.TranscriptionConfig(language_code=language_code)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_local_file)

    if transcript.status == aai.TranscriptStatus.error:
        print(transcript.error)
        raise Exception(transcript.error)
    else:
        return transcript.text
