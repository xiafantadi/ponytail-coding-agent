def clamp(value, low, high):
    return max(low, min(high, value))


def progress(completed, total):
    return round(completed / total * 100)
