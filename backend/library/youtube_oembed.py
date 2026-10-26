import logging

import requests

logger = logging.getLogger(__name__)

OEMBED_URL = "https://www.youtube.com/oembed"
OEMBED_TIMEOUT_SECONDS = 10


def fetch_channel_name(video_url: str) -> str | None:
    """Return the channel name of a YouTube video from the public oEmbed endpoint.

    Needs no API key and no yt-dlp, so it still works when yt-dlp metadata is
    unavailable.  Best effort: any failure (network, 4xx for a private or removed
    video, unexpected payload) yields None and never raises.
    """
    try:
        response = requests.get(
            OEMBED_URL, params={"url": video_url, "format": "json"}, timeout=OEMBED_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            logger.info("YouTube oEmbed answered %s for %s", response.status_code, video_url)
            return None
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("YouTube oEmbed failed for %s: %s", video_url, exc)
        return None
    name = payload.get("author_name") if isinstance(payload, dict) else None
    return (name.strip() or None) if isinstance(name, str) else None
