from yt_dlp import YoutubeDL

url="https://www.youtube.com/watch?v=j3jqNvEx0DI"

ydl_opts = {
    'cookiefile': 'cookies.txt',  # Upewnij się, że plik cookies jest poprawny.
    'outtmpl': f'tmp/youtube_to_text/j3jqNvEx0DI.mp4',
}

with YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])