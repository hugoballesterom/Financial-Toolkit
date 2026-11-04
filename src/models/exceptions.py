"""Custom exceptions shared across the toolkit."""


class RateLimitError(ConnectionError):
    """The data source rejected the request for exceeding its rate limit."""