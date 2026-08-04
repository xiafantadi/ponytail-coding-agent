def host(url):
    return url.split("://", 1)[-1].split("/", 1)[0].lower()
