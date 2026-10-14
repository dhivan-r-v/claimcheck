"""Deterministic scam signals: links and message patterns.

These run without any model call, so they are instant, free, and cannot be talked out of
a finding by a cleverly worded message.
"""
import ipaddress
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from .search import is_official

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "is.gd", "rb.gy", "shorturl.at",
    "tiny.cc", "ow.ly", "rebrand.ly", "s.id", "t.ly", "v.gd", "shorturl.asia",
}
RISKY_TLDS = {
    "xyz", "top", "click", "buzz", "live", "site", "online", "icu", "info", "shop", "club",
    "fun", "vip", "rest", "cfd", "sbs", "monster", "work", "loan", "win", "bid", "cyou",
}
# Words that make a non-official domain look official.
OFFICIAL_BAIT = (
    "gov", "govt", "sarkar", "yojana", "yojna", "kisan", "aadhaar", "aadhar", "uidai", "epfo",
    "irctc", "sbi", "rbi", "npci", "incometax", "itr", "refund", "kyc", "subsidy", "scheme",
    "pmkisan", "ration", "electricity", "bijli", "trai", "customs", "police", "cyber",
)
COMMON_TLDS = "com|in|org|net|co|xyz|top|click|buzz|live|site|online|icu|info|shop|club|fun|vip|ly|gl|gd|at|me|io|app|link|cfd|sbs|work|loan|win"

URL_RE = re.compile(
    rf"(?:https?://[^\s<>\"')\]]+)|(?:\b(?:[a-z0-9-]+\.)+(?:{COMMON_TLDS})\b(?:/[^\s<>\"')\]]*)?)",
    re.I,
)

PATTERNS = [
    # code, severity, label, regex
    ("asks_otp_pin", "critical", "Asks for an OTP, PIN or password",
     r"\botp\b|\bupi\s*pin\b|\bm-?pin\b|\bcvv\b|\bpassword\b|ओटीपी|पिन\s*(नंबर|बताएं|भेजें)"),
    ("apk_download", "critical", "Asks you to install an app file (.apk) outside the Play Store",
     r"\.apk\b|\bapk\s*(file|download)\b"),
    ("upfront_fee", "high", "Asks for a fee or payment to receive a benefit",
     r"(registration|processing|verification|activation|delivery)\s*(fee|charge|amount)|"
     r"\bpay\s*(only)?\s*(rs\.?|₹)\s*\d+|शुल्क|फीस"),
    ("threat", "high", "Threatens to block or cut off a service",
     r"(account|electricity|bijli|power|connection|sim|number|kyc|pan|aadhaa?r)\b.{0,40}"
     r"\b(block(ed)?|suspend(ed)?|disconnect(ed)?|deactivat\w*|cut|band)\b|"
     r"(बिजली|खाता|अकाउंट|सिम|कनेक्शन).{0,40}(कट|बंद|ब्लॉक)|"
     r"இணைப்பு.{0,30}துண்டி|துண்டிக்கப்படும்|முடக்கப்படும்"),
    ("prize", "high", "Promises a prize, lottery or lucky-draw win",
     r"\blottery\b|\blucky\s*draw\b|you\s*(have)?\s*won|\bjackpot\b|\bkbc\b|\bcongratulations\b.{0,40}\bwon\b"),
    ("urgency", "medium", "Pressures you to act immediately",
     r"\burgent(ly)?\b|\bimmediately\b|\btoday\s*only\b|\blast\s*(date|day|chance)\b|\bjaldi\b|"
     r"\bturant\b|\baaj\s*hi\b|\b(within|in)\s*\d+\s*(hours|hrs|minutes|mins)\b|\b\d+\s*ghante\b|तुरंत|जल्दी|"
     r"अंतिम\s*तिथि|உடனே|அவசர"),
    ("forward_chain", "medium", "Asks you to forward it to many people or groups",
     r"forward\s*(this|it)?\s*(to)?\s*\d+|share\s*(with|to|in)\s*\d+|\d+\s*groups|aage\s*bhej|"
     r"sab(ko|ke)\s*saath\s*share|फॉरवर्ड|शेयर\s*करें"),
]
_COMPILED = [(c, s, l, re.compile(p, re.I)) for c, s, l, p in PATTERNS]


@dataclass
class Flag:
    code: str
    severity: str  # critical | high | medium
    label: str
    evidence: str


def find_urls(text: str) -> list[str]:
    seen, out = set(), []
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:!?")
        if u.lower() not in seen:
            seen.add(u.lower())
            out.append(u)
    return out


def _host(url: str) -> str:
    if not re.match(r"https?://", url, re.I):
        url = "http://" + url
    return (urlparse(url).hostname or "").lower()


def check_url(url: str) -> list[Flag]:
    host = _host(url)
    if not host:
        return []
    flags: list[Flag] = []
    try:
        ipaddress.ip_address(host)
        return [Flag("ip_link", "critical", "Link points to a raw IP address, not a website name", url)]
    except ValueError:
        pass
    if is_official(host):
        return []
    labels = host.split(".")
    if "gov" in labels or "nic" in labels or "gov.in" in host:
        flags.append(Flag("fake_gov_domain", "critical",
                          "Link pretends to be a government site but is not a real .gov.in address", url))
    elif any(b in host for b in OFFICIAL_BAIT):
        flags.append(Flag("lookalike_domain", "critical",
                          "Link uses official-sounding words but is not an official website", url))
    if host.startswith("xn--") or ".xn--" in host:
        flags.append(Flag("punycode", "high", "Link uses look-alike characters (punycode)", url))
    if host in SHORTENERS:
        flags.append(Flag("shortener", "high", "Link is shortened, hiding where it really goes", url))
    if labels[-1] in RISKY_TLDS:
        flags.append(Flag("risky_tld", "high", f"Link uses a '.{labels[-1]}' address, common in scams", url))
    if url.lower().startswith("http://"):
        flags.append(Flag("no_https", "medium", "Link is not secure (http, not https)", url))
    return flags


def analyse(text: str) -> dict:
    flags: list[Flag] = []
    urls = find_urls(text)
    for u in urls:
        flags += check_url(u)
    for code, sev, label, rx in _COMPILED:
        m = rx.search(text)
        if m:
            flags.append(Flag(code, sev, label, m.group(0).strip()[:80]))
    order = {"critical": 0, "high": 1, "medium": 2}
    flags.sort(key=lambda f: order[f.severity])
    return {
        "urls": urls,
        "official_urls": [u for u in urls if is_official(_host(u))],
        "flags": [asdict(f) for f in flags],
        "critical": any(f.severity == "critical" for f in flags),
    }
