class AiResponse:
    def __init__(self, query, model=None):
        self.cached = False
        self.query = query
        self.model = model
        self.response_text = None
        self.temperature = None
        self.max_token_count = None
        self.top_p = None
        self.input_tokens = None
        self.output_tokens = None
        self.total_tokens = None
        self.prompt_tokens = None
        self.completion_tokens = None
        self.id = None
