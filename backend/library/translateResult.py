class TranslateResult:
    def __init__(self, text: str, target_language: str, source_language: str, translated_text: str = None,
                 status: str = "success", error_message: str = None, cached: bool = False):
        self.text = text
        self.target_language = target_language
        self.source_language = source_language
        self.translated_text = translated_text
        self.status = status
        self.error_message = error_message
        self.cached = cached
