def is_retryable(status):
    return status in {500, 502, 503}
