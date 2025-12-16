"""
Country code extraction service.

Uses static pattern matching with LLM fallback (Qwen via OpenRouter).
Caches results in MongoDB for reuse.
"""

import os
import re
from typing import Optional

import httpx

# Static mapping for common patterns
# Keys are regex patterns, values are 2-letter ISO country codes
COUNTRY_PATTERNS = {
    # Ireland
    r"\bireland\b": "IE",
    r"\bdublin\b": "IE",
    r"\bcork\b": "IE",
    r"\bgalway\b": "IE",
    r"\blimerick\b": "IE",
    # Germany
    r"\bgermany\b": "DE",
    r"\bberlin\b": "DE",
    r"\bmunich\b": "DE",
    r"\bfrankfurt\b": "DE",
    r"\bhamburg\b": "DE",
    r"\bdusseldorf\b": "DE",
    r"\bd[uü]sseldorf\b": "DE",
    r"\bm[uü]nchen\b": "DE",
    r"\bcologne\b": "DE",
    r"\bk[oö]ln\b": "DE",
    # France
    r"\bfrance\b": "FR",
    r"\bparis\b": "FR",
    r"\blyon\b": "FR",
    r"\bmarseille\b": "FR",
    r"\btoulouse\b": "FR",
    # UK
    r"\bunited kingdom\b": "GB",
    r"\blondon\b": "GB",
    r"\buk\b": "GB",
    r"\bengland\b": "GB",
    r"\bscotland\b": "GB",
    r"\bwales\b": "GB",
    r"\bmanchester\b": "GB",
    r"\bbirmingham\b": "GB",
    r"\bedinburgh\b": "GB",
    r"\bbristol\b": "GB",
    r"\bleeds\b": "GB",
    r"\bcambridge\b": "GB",
    r"\boxford\b": "GB",
    # Netherlands
    r"\bnetherlands\b": "NL",
    r"\bamsterdam\b": "NL",
    r"\bholland\b": "NL",
    r"\brotterdam\b": "NL",
    r"\bthe hague\b": "NL",
    r"\butrecht\b": "NL",
    r"\beindhoven\b": "NL",
    # Poland
    r"\bpoland\b": "PL",
    r"\bwarsaw\b": "PL",
    r"\bkrakow\b": "PL",
    r"\bkrak[oó]w\b": "PL",
    r"\bwroclaw\b": "PL",
    r"\bwroc[lł]aw\b": "PL",
    r"\bgdansk\b": "PL",
    r"\bgda[nń]sk\b": "PL",
    r"\bpoznan\b": "PL",
    r"\bpozna[nń]\b": "PL",
    r"\bwarszawa\b": "PL",
    # Denmark
    r"\bdenmark\b": "DK",
    r"\bcopenhagen\b": "DK",
    r"\bk[oø]benhavn\b": "DK",
    # Italy
    r"\bitaly\b": "IT",
    r"\brome\b": "IT",
    r"\bmilan\b": "IT",
    r"\bmilano\b": "IT",
    r"\bturin\b": "IT",
    r"\btorino\b": "IT",
    # Spain
    r"\bspain\b": "ES",
    r"\bmadrid\b": "ES",
    r"\bbarcelona\b": "ES",
    r"\bvalencia\b": "ES",
    r"\bseville\b": "ES",
    # Sweden
    r"\bsweden\b": "SE",
    r"\bstockholm\b": "SE",
    r"\bgothenburg\b": "SE",
    r"\bmalmo\b": "SE",
    r"\bmalm[oö]\b": "SE",
    # Norway
    r"\bnorway\b": "NO",
    r"\boslo\b": "NO",
    r"\bbergen\b": "NO",
    # Finland
    r"\bfinland\b": "FI",
    r"\bhelsinki\b": "FI",
    # Belgium
    r"\bbelgium\b": "BE",
    r"\bbrussels\b": "BE",
    r"\bbrussel\b": "BE",
    r"\bantwerp\b": "BE",
    r"\bantwerpen\b": "BE",
    # Austria
    r"\baustria\b": "AT",
    r"\bvienna\b": "AT",
    r"\bwien\b": "AT",
    r"\bgraz\b": "AT",
    # Switzerland
    r"\bswitzerland\b": "CH",
    r"\bzurich\b": "CH",
    r"\bz[uü]rich\b": "CH",
    r"\bgeneva\b": "CH",
    r"\bgen[eè]ve\b": "CH",
    r"\bbasel\b": "CH",
    r"\bbern\b": "CH",
    # Portugal
    r"\bportugal\b": "PT",
    r"\blisbon\b": "PT",
    r"\blisboa\b": "PT",
    r"\bporto\b": "PT",
    # USA
    r"\bunited states\b": "US",
    r"\busa\b": "US",
    r"\bamerica\b": "US",
    r"\bnew york\b": "US",
    r"\bsan francisco\b": "US",
    r"\blos angeles\b": "US",
    r"\bseattle\b": "US",
    r"\bboston\b": "US",
    r"\bchicago\b": "US",
    r"\baustin\b": "US",
    r"\bdenver\b": "US",
    r"\batlanta\b": "US",
    # Canada
    r"\bcanada\b": "CA",
    r"\btoronto\b": "CA",
    r"\bvancouver\b": "CA",
    r"\bmontreal\b": "CA",
    r"\bottawa\b": "CA",
    r"\bcalgary\b": "CA",
    # Australia
    r"\baustralia\b": "AU",
    r"\bsydney\b": "AU",
    r"\bmelbourne\b": "AU",
    r"\bbrisbane\b": "AU",
    # Czech Republic
    r"\bczech\b": "CZ",
    r"\bczechia\b": "CZ",
    r"\bprague\b": "CZ",
    r"\bpraha\b": "CZ",
    r"\bbrno\b": "CZ",
    # Hungary
    r"\bhungary\b": "HU",
    r"\bbudapest\b": "HU",
    # Romania
    r"\bromania\b": "RO",
    r"\bbucharest\b": "RO",
    r"\bbucharesti\b": "RO",
    r"\bcluj\b": "RO",
    # India
    r"\bindia\b": "IN",
    r"\bbangalore\b": "IN",
    r"\bmumbai\b": "IN",
    r"\bhyderabad\b": "IN",
    r"\bpune\b": "IN",
    r"\bgurgaon\b": "IN",
    r"\bnoida\b": "IN",
    # Singapore
    r"\bsingapore\b": "SG",
    # Japan
    r"\bjapan\b": "JP",
    r"\btokyo\b": "JP",
    # Luxembourg
    r"\bluxembourg\b": "LU",
    # Greece
    r"\bgreece\b": "GR",
    r"\bathens\b": "GR",
    # Israel
    r"\bisrael\b": "IL",
    r"\btel aviv\b": "IL",
    # UAE
    r"\bdubai\b": "AE",
    r"\babu dhabi\b": "AE",
    r"\buae\b": "AE",
    r"\bunited arab emirates\b": "AE",
    # Remote - special code
    r"\bremote\b": "RMT",
    r"\bwork from home\b": "RMT",
    r"\bwfh\b": "RMT",
    r"\bhybrid\b": "HYB",
}


def extract_from_pattern(location: str) -> Optional[str]:
    """
    Try to extract country code using static patterns.

    Args:
        location: Location string from job posting

    Returns:
        2-letter ISO country code, 'RMT' for remote, or None if no match
    """
    if not location:
        return None

    location_lower = location.lower()

    for pattern, code in COUNTRY_PATTERNS.items():
        if re.search(pattern, location_lower):
            return code

    return None


async def extract_country_code_llm(location: str) -> Optional[str]:
    """
    Extract country code using cheap LLM (Qwen via OpenRouter).

    Falls back to LLM when static patterns don't match.

    Args:
        location: Location string from job posting

    Returns:
        2-letter ISO country code or None if extraction fails
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f'Extract the 2-letter ISO country code from this location: "{location}". '
                                'Return ONLY the 2-letter code (e.g., "DE", "FR", "US") or "RMT" if it mentions '
                                'remote work. If you cannot determine the country, return "??".'
                            ),
                        }
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                code = data["choices"][0]["message"]["content"].strip().upper()
                # Validate: should be 2-3 chars and alphabetic
                if len(code) <= 3 and code.isalpha():
                    return code
    except Exception as e:
        print(f"[Country Code] LLM extraction failed: {e}")

    return None


def get_country_code_sync(location: str) -> str:
    """
    Synchronous wrapper - try static pattern only.

    For use in sync contexts where LLM fallback is not needed.

    Args:
        location: Location string from job posting

    Returns:
        2-letter ISO country code, 'RMT' for remote, 'HYB' for hybrid, or '??' if unknown
    """
    code = extract_from_pattern(location)
    return code if code else "??"


async def get_country_code(location: str, db=None, job_id=None) -> str:
    """
    Get country code with LLM fallback and optional caching.

    1. Try static pattern matching
    2. Fall back to LLM if no match
    3. Cache result in MongoDB if db and job_id provided

    Args:
        location: Location string from job posting
        db: Optional MongoDB database instance for caching
        job_id: Optional job ID (ObjectId or str) for caching

    Returns:
        2-letter ISO country code, 'RMT' for remote, 'HYB' for hybrid, or '??' if unknown
    """
    # First try static patterns
    code = extract_from_pattern(location)

    if not code:
        # Try LLM fallback
        code = await extract_country_code_llm(location)

    if not code:
        code = "??"

    # Cache in MongoDB if possible
    if db and job_id and code != "??":
        try:
            await db["level-2"].update_one(
                {"_id": job_id}, {"$set": {"country_code": code}}
            )
        except Exception as e:
            print(f"[Country Code] Failed to cache: {e}")

    return code
