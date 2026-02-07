class EmbeddingResult:
    def __init__(self, text: str, model_id: str = None, embedding=None,
                 status: str = "success", error_message: str = None, input_text_token_count: int = None):
        self.text = text
        self.embedding = embedding
        self.status = status
        self.status_code = -1
        self.model_id = model_id
        self.error_message = error_message
        self.input_text_token_count = input_text_token_count

