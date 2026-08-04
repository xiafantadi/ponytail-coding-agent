from pathlib import Path


def safe_join(root, relative):
    return str(Path(root) / relative)
