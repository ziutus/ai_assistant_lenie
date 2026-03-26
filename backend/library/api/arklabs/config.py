API_BASE_DEFAULT = "https://api.ark-labs.cloud/api/v1"


def get_arklabs_config():
    """Pobierz klucz API i bazowy URL ARK Labs z konfiguracji."""
    from library.config_loader import load_config
    cfg = load_config()
    key = cfg.get("ARK_LABS_KEY")
    if not key:
        raise RuntimeError("ARK_LABS_KEY is not set in configuration")
    base_url = cfg.get("ARK_LABS_URL") or API_BASE_DEFAULT
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"
    if not base_url.endswith("/api/v1"):
        base_url = base_url.rstrip("/") + "/api/v1"
    return key, base_url
