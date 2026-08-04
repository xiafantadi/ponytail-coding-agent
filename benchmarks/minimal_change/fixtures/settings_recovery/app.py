import json


def load_settings(text, previous):
    try:
        return json.loads(text)
    except ValueError:
        return {}
