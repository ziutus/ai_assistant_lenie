"""Webshare proxy IP authorization and bandwidth check helper.

Ensures the current public IP is authorized in Webshare so that
rotating residential proxies work without manual dashboard changes.
Also checks remaining bandwidth to avoid wasting requests when the
monthly limit is exhausted.
"""

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

WEBSHARE_IP_CHECK_URL = "https://ipv4.webshare.io/"
WEBSHARE_API_BASE = "https://proxy.webshare.io/api/v2/"
MIN_BANDWIDTH_BYTES = 10 * 1024 * 1024  # 10 MB


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Token {api_key}"}


def get_proxy_credentials(api_key: str) -> tuple[str, str] | None:
    """Fetch Webshare proxy username and password from the API.

    Returns:
        (proxy_username, proxy_password) tuple, or None on failure.
    """
    resp = requests.get(f"{WEBSHARE_API_BASE}proxy/config/", headers=_headers(api_key), timeout=10)
    if not resp.ok:
        logger.warning(f"Could not fetch Webshare proxy credentials: {resp.status_code} — {resp.text}")
        return None
    data = resp.json()
    username = data.get("proxy_username") or data.get("username")
    password = data.get("proxy_password") or data.get("password")
    if not username or not password:
        logger.warning(f"Webshare proxy config missing username/password: {data}")
        return None
    return username, password


def get_current_ip() -> str:
    """Get current public IPv4 address via Webshare's IP check service."""
    resp = requests.get(WEBSHARE_IP_CHECK_URL, timeout=10)
    resp.raise_for_status()
    return resp.text.strip()


def ensure_ip_authorized(api_key: str, expected_ip: str = None) -> str:
    """Ensure current IP is authorized in Webshare. Returns the authorized IP.

    Args:
        api_key: Webshare API key (Token).
        expected_ip: If set, verify that current IP matches this value.

    Returns:
        The current public IP address.

    Raises:
        SystemExit: If IP mismatch with expected_ip.
    """
    headers = _headers(api_key)
    current_ip = get_current_ip()
    logger.info(f"Current public IP: {current_ip}")

    if expected_ip and current_ip != expected_ip:
        logger.error(f"IP mismatch! Current: {current_ip}, expected: {expected_ip}")
        raise SystemExit(1)

    resp = requests.get(f"{WEBSHARE_API_BASE}proxy/ipauthorization/", headers=headers, timeout=10)
    if not resp.ok:
        logger.error(f"Webshare GET ipauthorization failed: {resp.status_code} — {resp.text}")
    resp.raise_for_status()

    existing = resp.json()["results"]
    authorized_ips = [entry["ip_address"] for entry in existing]

    if current_ip in authorized_ips:
        logger.info(f"IP {current_ip} is already authorized in Webshare")
        return current_ip

    resp = requests.post(
        f"{WEBSHARE_API_BASE}proxy/ipauthorization/",
        json={"ip_address": current_ip},
        headers=headers,
        timeout=10,
    )

    if resp.status_code == 400:
        error_codes = [e.get("code") for item in resp.json().values() for e in (item if isinstance(item, list) else [])]
        if "not_enough_ip_authorizations" in error_codes and existing:
            logger.info(f"IP authorization limit reached — replacing old IPs with {current_ip}")
            for entry in existing:
                del_resp = requests.delete(
                    f"{WEBSHARE_API_BASE}proxy/ipauthorization/{entry['id']}/",
                    headers=headers,
                    timeout=10,
                )
                if del_resp.ok:
                    logger.info(f"Removed old authorized IP: {entry['ip_address']}")
                else:
                    logger.warning(f"Failed to remove IP {entry['ip_address']}: {del_resp.status_code} — {del_resp.text}")
            resp = requests.post(
                f"{WEBSHARE_API_BASE}proxy/ipauthorization/",
                json={"ip_address": current_ip},
                headers=headers,
                timeout=10,
            )

    if not resp.ok:
        logger.error(f"Webshare POST ipauthorization failed: {resp.status_code} — {resp.text}")
    resp.raise_for_status()
    logger.info(f"IP {current_ip} authorized in Webshare")
    return current_ip


def check_bandwidth(api_key: str) -> dict:
    """Check Webshare bandwidth usage for current month.

    Returns:
        Dict with keys: available (bool), used_mb, limit_mb, remaining_mb.
    """
    headers = _headers(api_key)

    profile_resp = requests.get(f"{WEBSHARE_API_BASE}profile/", headers=headers, timeout=10)
    if profile_resp.ok:
        p = profile_resp.json()
        logger.info(f"Webshare account: {p.get('email')}")
    else:
        logger.warning(f"Could not fetch Webshare profile: {profile_resp.status_code}")

    resp = requests.get(f"{WEBSHARE_API_BASE}subscription/plan/", headers=headers, timeout=10)
    resp.raise_for_status()
    plans = resp.json()["results"]

    active_plan = next((p for p in plans if p["status"] == "active"), None)
    if active_plan is None:
        logger.warning("No active Webshare plan found")
        return {"available": False, "used_mb": 0, "limit_mb": 0, "remaining_mb": 0}

    plan_type = f"{active_plan.get('proxy_type', '?')}/{active_plan.get('proxy_subtype', '?')}"
    logger.info(f"Webshare plan: {plan_type}, ${active_plan.get('monthly_price')}/mo, {active_plan.get('proxy_count', 0):,} proxies")

    raw_limit = active_plan.get("bandwidth_limit", 0)
    if not raw_limit:
        logger.info("Webshare plan: unlimited bandwidth — proxy available")
        return {"available": True, "used_mb": 0, "limit_mb": 0, "remaining_mb": -1}

    bandwidth_limit_bytes = raw_limit * 1024 * 1024 * 1024  # API returns GB

    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    resp = requests.get(
        f"{WEBSHARE_API_BASE}stats/aggregate/",
        params={"timestamp__gte": start_of_month.isoformat(), "timestamp__lte": now.isoformat()},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    stats = resp.json()

    bandwidth_used = stats.get("bandwidth_total", 0)
    bandwidth_remaining = bandwidth_limit_bytes - bandwidth_used

    used_mb = round(bandwidth_used / 1048576)
    limit_mb = round(bandwidth_limit_bytes / 1048576)
    remaining_mb = round(bandwidth_remaining / 1048576)
    available = bandwidth_remaining > MIN_BANDWIDTH_BYTES

    logger.info(f"Webshare bandwidth: {used_mb:.1f} MB used / {limit_mb:.0f} MB limit ({remaining_mb} MB remaining)")

    if not available:
        logger.warning(f"Webshare bandwidth nearly exhausted ({remaining_mb} MB remaining) — proxy disabled")

    return {"available": available, "used_mb": used_mb, "limit_mb": limit_mb, "remaining_mb": remaining_mb}
