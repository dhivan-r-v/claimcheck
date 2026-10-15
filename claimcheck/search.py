"""Tavily search + extract, and helpers to turn results into numbered evidence."""
import hashlib
import json
import re
from urllib.parse import urlparse

import httpx

from . import config

TAVILY = "https://api.tavily.com"


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    # Optional disk cache (set SEARCH_CACHE_DIR) so evaluation reruns don't spend Tavily credits.
    cache_file = None
    if config.SEARCH_CACHE_DIR:
        key = hashlib.sha256(json.dumps([path, body], sort_keys=True).encode()).hexdigest()
        cache_file = config.SEARCH_CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
    r = await client.post(
        f"{TAVILY}/{path}",
        json=body,
        headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    include_domains: list[str] | None = None,
    topic: str = "general",
    depth: str = "basic",
    time_range: str | None = None,
    max_results: int = 4,
) -> list[dict]:
    body = {"query": query, "topic": topic, "search_depth": depth, "max_results": max_results}
    if include_domains:
        body["include_domains"] = include_domains
    if time_range:
        body["time_range"] = time_range
    try:
        data = await _post(client, "search", body)
    except httpx.HTTPError:
        return []
    return data.get("results", [])


async def extract(client: httpx.AsyncClient, urls: list[str]) -> dict[str, str]:
    """Full page text for each URL (Tavily Extract)."""
    if not urls:
        return {}
    try:
        data = await _post(client, "extract", {"urls": urls, "extract_depth": "basic"})
    except httpx.HTTPError:
        return {}
    return {r["url"]: r.get("raw_content") or "" for r in data.get("results", [])}


_JUNK = ("javascript must be enabled", "enable javascript", "please enable cookies", "access denied")


def is_junk(text: str | None) -> bool:
    """Search results / pages with no usable content (JS walls, error pages)."""
    t = (text or "").strip().lower()
    return len(t) < 40 or (len(t) < 400 and any(j in t for j in _JUNK))


def article_key(url: str, title: str) -> str:
    """Identify one article across URL variants (AMP, tracking params, trailing slashes, mirrors)."""
    norm_title = re.sub(r"\W+", " ", (title or "").lower()).strip()
    if len(norm_title) >= 20:
        return f"{domain(url)}|{norm_title}"
    u = urlparse(url)
    # Keep the query (PIB releases differ only by ?PRID=...) but drop tracking parameters.
    query = "&".join(sorted(p for p in u.query.split("&") if p and not p.lower().startswith(("utm_", "fbclid", "gclid"))))
    return f"{domain(url)}{u.path.rstrip('/').removesuffix('/amp')}?{query}"


def domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def is_official(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return host.endswith(config.OFFICIAL_SUFFIXES) or any(
        host == d or host.endswith("." + d) for d in config.OFFICIAL_DOMAINS
    )


def relevant_passages(text: str, keywords: list[str], limit: int = 2500) -> str:
    """Keep the paragraphs of a long page that mention the claim's keywords."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) > 40]
    kws = {k.lower() for k in keywords if len(k) > 2}
    scored = sorted(paras, key=lambda p: -sum(k in p.lower() for k in kws))
    out, size = [], 0
    for p in scored:
        if size + len(p) > limit:
            break
        out.append(p)
        size += len(p)
    return "\n".join(out)
