import logging
import os
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL

from library.text_transcript import text_split_with_chapters

logger = logging.getLogger(__name__)

# Audio-only: transcription (AssemblyAI) never needs the video track, and a
# single audio stream needs no ffmpeg merge step (unlike separate DASH
# video+audio streams for anything above 360p).
_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"

_METADATA_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "format": _AUDIO_FORMAT,
}


class StalkerYoutubeFile:
    def __init__(self, youtube_url: str, media_type: str, cache_directory: str, chapters_string: str = None):

        if media_type not in ["video"]:
            raise Exception(f"Type {media_type} must be either video or audio (tbd)")

        self.url: str = youtube_url
        parsed_url = urlparse(youtube_url)
        if parsed_url.netloc not in ['youtu.be', 'www.youtube.com', 'youtube.com']:
            self.error = f"ERROR: Invalid YouTube URL: {self.url}. URL should start with 'youtu.be' or 'www.youtube.com'"

        self.valid: bool = True
        self.error = None
        self.private = False

        # Whether yt-dlp could fetch title/author/description/length for this
        # video. False on bot-detection, private/login-required, deleted, etc.
        # — captions can still be fetched independently via youtube_transcript_api.
        self.metadata_available: bool = True

        self.title = None
        self.author = None
        self.description = None
        self.length_seconds = None
        self.length_minutes = None

        self.filename = None
        self.type = None
        self.directory = cache_directory
        self.video_id = None
        self.text = None
        self.transcript_file = None
        self.summary_filename = None
        self.text_file = None
        self.transcription_done: bool = False
        self.transcript_string: str | None = None
        self.chapters_string = chapters_string

        resolved_ext = "m4a"

        try:
            with YoutubeDL(_METADATA_YDL_OPTS) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
            self.video_id = info.get('id')
            self.title = info.get('title')
            self.author = info.get('uploader')
            self.description = info.get('description')
            self.length_seconds = info.get('duration')
            self.length_minutes = round(self.length_seconds / 60, 2) if self.length_seconds else None
            resolved_ext = info.get('ext') or resolved_ext
        except Exception as e:
            logger.warning(f"yt-dlp metadata extraction failed for {youtube_url}: {e}")
            self.metadata_available = False
            if 'private' in str(e).lower() or 'sign in' in str(e).lower():
                self.private = True
            # Metadata failed, but captions are fetched independently — recover
            # video_id from the URL so that path still works.
            qs = parse_qs(parsed_url.query)
            if 'v' in qs:
                self.video_id = qs['v'][0]
            elif parsed_url.netloc == 'youtu.be':
                self.video_id = parsed_url.path.lstrip('/')

        if self.video_id and media_type == "video":
            self.filename = f'{self.video_id}.{resolved_ext}'

        self.path = f"{self.directory}/{self.filename}" if self.directory and self.filename else None

        if self.video_id:
            self.transcript_file = self.directory + "/" + self.video_id + "_transcription.json"
            self.summary_filename = self.directory + "/" + self.video_id + "_summary.txt"
            self.text_file = self.directory + "/" + self.video_id + "_text.txt"

        if self.text_file and os.path.exists(self.text_file):
            with open(self.text_file, 'r', encoding='utf-8') as file:
                self.text = file.read()

        self.transcription_load_from_file()

    def transcription_load_from_file(self, filename: str = None) -> bool:
        if filename is None:
            filename = self.transcript_file

        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as file:
                self.transcript_string = file.read()
                return True
        return False

    def transcription_split_by_chapters(self) -> str:
        if len(self.chapters_string) > 0:
            self.text = text_split_with_chapters(self.transcript_string, chapters_string=self.chapters_string)
        else:
            self.text = self.transcript_string
        return self.text

    def save_in_local_cache(self, verbose=False) -> None:
        if len(self.text) > 3:
            if verbose:
                print("Writing text to file: {self.text_file}", end=" ")
            with open(self.text_file, 'w', encoding="utf8") as file:
                file.write(self.text)
            if verbose:
                print("[DONE]")

    def download_video(self, force: bool = False) -> None:

        if not os.path.exists(self.directory):
            raise Exception(f"Directory {self.directory} doesn't exist")

        if os.path.exists(self.path) and not force:
            return

        if not self.metadata_available:
            self.valid = False
            self.error = "Can't download youtube video: metadata unavailable"
            raise Exception(self.error)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": _AUDIO_FORMAT,
            "outtmpl": self.path,
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            self.valid = False
            self.error = f"Can't download youtube video: {e}"
            raise Exception(self.error) from e
