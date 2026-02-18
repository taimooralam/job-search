"""Cookie parser for LinkedIn authentication.

Reads Netscape-format cookie files (exported via browser extension)
and extracts the tokens needed by the linkedin-api library.
"""

from datetime import datetime, timezone
from pathlib import Path

from requests.cookies import RequestsCookieJar

from utils import setup_logging

logger = setup_logging("linkedin-cookies")

REQUIRED_COOKIES = ["li_at", "JSESSIONID"]
OPTIONAL_COOKIES = ["bcookie", "bscookie", "li_mc"]

DEFAULT_COOKIE_PATH = "/home/node/linkedin-cookies.txt"


def load_cookies(path: str = DEFAULT_COOKIE_PATH) -> dict[str, str]:
    """Parse a Netscape-format cookie file and return a name→value dict.

    Netscape format: domain  flag  path  secure  expiry  name  value
    Lines starting with # are comments. Empty lines are skipped.
    """
    cookie_file = Path(path)
    if not cookie_file.exists():
        raise FileNotFoundError(f"Cookie file not found: {path}")

    cookies = {}
    for line in cookie_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name, value = parts[5], parts[6]
            cookies[name] = value

    logger.info("Loaded %d cookies from %s", len(cookies), path)
    return cookies


def get_linkedin_auth(path: str = DEFAULT_COOKIE_PATH) -> RequestsCookieJar:
    """Extract the authentication cookies needed by linkedin-api.

    Returns a RequestsCookieJar (not a plain dict) because the linkedin-api
    library's _set_session_cookies expects a jar with .extract_cookies() support.

    Raises:
        ValueError: If required cookies are missing.
    """
    cookies = load_cookies(path)

    for name in REQUIRED_COOKIES:
        if name not in cookies:
            raise ValueError(f"Required cookie '{name}' not found in {path}")

    jar = RequestsCookieJar()
    for name in REQUIRED_COOKIES + OPTIONAL_COOKIES:
        if name in cookies:
            jar.set(name, cookies[name], domain=".linkedin.com", path="/")

    return jar


def validate_cookies(path: str = DEFAULT_COOKIE_PATH) -> dict:
    """Validate that cookies exist, are present, and check expiry.

    Returns:
        Dict with 'valid', 'missing', 'expired' keys.
    """
    result = {"valid": True, "missing": [], "expired": [], "present": []}

    try:
        cookies_raw = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return {"valid": False, "missing": REQUIRED_COOKIES, "expired": [], "present": [], "error": "File not found"}

    cookie_data = {}
    for line in cookies_raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5]
            expiry = int(parts[4]) if parts[4].isdigit() else 0
            cookie_data[name] = expiry

    now_ts = int(datetime.now(timezone.utc).timestamp())

    for name in REQUIRED_COOKIES:
        if name not in cookie_data:
            result["missing"].append(name)
            result["valid"] = False
        elif cookie_data[name] > 0 and cookie_data[name] < now_ts:
            result["expired"].append(name)
            result["valid"] = False
        else:
            result["present"].append(name)

    return result


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test LinkedIn cookie parsing")
    parser.add_argument("--test", action="store_true", help="Validate cookies")
    parser.add_argument("--path", default=DEFAULT_COOKIE_PATH, help="Cookie file path")
    args = parser.parse_args()

    if args.test:
        validation = validate_cookies(args.path)
        logger.info("Cookie validation: %s", validation)

        if validation["valid"]:
            auth = get_linkedin_auth(args.path)
            logger.info("Auth cookies extracted: %s", list(auth.keys()))
            # Show truncated li_at for verification
            li_at = auth.get("li_at", "")
            logger.info("li_at: %s...%s", li_at[:8], li_at[-8:] if len(li_at) > 16 else "")
