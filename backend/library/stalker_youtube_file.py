import logging
import os
from pprint import pprint
from urllib.parse import urlparse, parse_qs

from pytubefix import YouTube
from yt_dlp import YoutubeDL

from library.text_transcript import text_split_with_chapters

logger = logging.getLogger(__name__)


class StalkerYoutubeFile:
    def __init__(self, youtube_url: str, media_type: str, cache_directory: str, chapters_string: str = None):

        if media_type not in ["video"]:
            pprint(media_type)
            raise Exception(f"Type {media_type} must be either video or audio (tbd)")

        self.url: str = youtube_url
        parsed_url = urlparse(youtube_url)
        if parsed_url.netloc not in ['youtu.be', 'www.youtube.com', 'youtube.com']:
            self.error = f"ERROR: Invalid YouTube URL: {self.url}. URL should start with 'youtu.be' or 'www.youtube.com'"

        self.valid: bool = True
        self.error = None
        self.private = False

        self.can_pytube: bool = True
        self.can_YoutubeDL: bool = True

        self.title = None
        self.author = None
        self.description = None
        self.length_seconds = None
        self.length_minutes = None

        self._yt = None
        self.filename = None
        self.type = None
        self.directory = None
        self.video_id = None
        self.text = None
        self.transcript_file = None
        self.summary_filename = None
        self.text_file = None
        self.transcription_done: bool = False
        self.transcript_string: str | None = None

        self.directory = cache_directory
        self.chapters_string = chapters_string

        try:
            self._yt = YouTube(youtube_url)
        except Exception as e:
            logger.warning(f"pytube failed for {youtube_url}: {e}")
            self.can_pytube = False

        if self._yt:
            if media_type == "video":
                self.filename = f'{self._yt.video_id}.mp4'

            if self._yt.vid_info['playabilityStatus']['status'] == 'LOGIN_REQUIRED':
                self.can_pytube = False
                self.private = True

            self.video_id = self._yt.video_id

            if self.can_pytube:
                self.title = f"{self._yt.title}"
                self.author = f"{self._yt.author}"
                self.description = f"{self._yt.description}"
                self.length_seconds = self._yt.length
                self.length_minutes = round(self._yt.length / 60, 2)
        else:
            # Extract video_id from URL when pytube fails
            parsed = urlparse(youtube_url)
            qs = parse_qs(parsed.query)
            if 'v' in qs:
                self.video_id = qs['v'][0]
            elif parsed.netloc == 'youtu.be':
                self.video_id = parsed.path.lstrip('/')
            if self.video_id and media_type == "video":
                self.filename = f'{self.video_id}.mp4'

        self.directory = cache_directory
        self.type = None

        self.chapters_string = chapters_string

        self.transcript_file = None
        self.transcription_done: bool = False
        self.transcript_string: str | None = None
        self.summary_filename = None
        self.text_file = None

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

        if not os.path.exists(f"{self.directory}/{self.filename}") or force:
            if self.can_pytube:
                yt_stream = self._yt.streams.first()
                if yt_stream:
                    self._yt.streams.first().download(max_retries=3, output_path=self.directory,
                                                      filename=self.filename,
                                                      skip_existing=False)
                    self.type = self._yt.streams.first().type
                else:
                    self.valid = False
                    self.error = "Can't find stream for this youtube video"
                    raise Exception("Can't find stream for this youtube video")
            elif self.can_YoutubeDL:
                ydl_opts = {
                    'cookiefile': 'cookies.txt',
                    'outtmpl': f"{self.directory}/{self.filename}",
                }

                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.url])
            else:
                self.valid = False
                self.error = "Can't download youtube video"
                raise Exception("Can't download youtube video")

        # TODO: Write metadata for youtube file
        # if not os.path.exists(f"{self.directory}/{self.video_id}.json") or force:
        #     with open(f"{self.directory}/{self.video_id}.json", "w", encoding="utf8") as json_file:
        #         json.dump(json_data, json_file, indent=4)
