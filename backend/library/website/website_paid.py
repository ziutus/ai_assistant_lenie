import urllib.parse


def website_is_paid(link: str) -> bool:
    parsed_url = urllib.parse.urlparse(link)
    domain = parsed_url.netloc
    path = parsed_url.path

    if domain in ["wyborcza.pl", "wyborcza.biz"]:
        return True

    if domain == "onet.pl":
        if path.find("newsweek"):
            return True
        if path.find("premium"):
            return True
        if path.find("businessinsider"):
            return True

    return False
