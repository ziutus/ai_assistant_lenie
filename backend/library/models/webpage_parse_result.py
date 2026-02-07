class WebPageParseResult:
    def __init__(self, url: str) -> None:
        self.text_raw = None
        self.text = None
        self.url = url
        self.language: str | None = None
        self.title: str | None = None
        self.summary: str | None = None
