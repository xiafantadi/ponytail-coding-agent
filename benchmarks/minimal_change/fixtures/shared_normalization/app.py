_records = {}


def normalize_key(value):
    return value.strip().lower()


def put(key, value):
    _records[normalize_key(key)] = value


def get(key):
    return _records.get(key)
