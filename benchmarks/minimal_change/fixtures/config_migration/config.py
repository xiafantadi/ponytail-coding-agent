def read_timeout(config):
    return config.get("timeout_ms", 1000)
