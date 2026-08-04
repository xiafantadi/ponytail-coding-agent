def parse_version(value):
    return tuple(int(part) for part in value.split("."))
