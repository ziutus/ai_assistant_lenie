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
        # UsageRecord from library.llm_usage.recorder (tokens, latency,
        # usage_log_id, cost summary with status), set by ai_ask() after each
        # call. Cost lives ONLY here — never add cost_usd/cost/credits_used
        # attributes to this class (see docs/search-rebuild-implementation-plan.md,
        # stages 3/3b).
        self.usage = None
