class EmbeddingResults:
    def __init__(self, text: [str], model_id: str = None, embedding=None,
                 status: str = "success", status_code: int = -1, error_message: str = None, input_text_token_count: int = None):
        self.text = text
        self.embedding = embedding
        self.status = status
        self.status_code = status_code
        self.model_id = model_id
        self.error_message = error_message
        # tokens values
        self.input_text_token_count = input_text_token_count
        # prompt_tokens - reported by cloudferro (old openAI api)
        self.prompt_tokens = None
        # total_tokens - reported by cloudferro (old openAI api)
        self.total_tokens = None
