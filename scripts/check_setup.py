"""Sanity-check API keys: list Token Factory models and make one Tavily call.

Usage: python scripts/check_setup.py
Never prints key values.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def request(url, *, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300]
    except urllib.error.URLError as e:
        return None, str(e.reason)


def main():
    env = load_env(ROOT / ".env")
    ok = True

    base = env.get("NEBIUS_BASE_URL", "").rstrip("/")
    status, data = request(
        f"{base}/models", headers={"Authorization": f"Bearer {env.get('NEBIUS_API_KEY', '')}"}
    )
    print(f"== Token Factory  {base}/models -> {status}")
    if status == 200:
        ids = sorted(m["id"] for m in data.get("data", []))
        nvidia = [i for i in ids if "nvidia" in i.lower() or "nemotron" in i.lower()]
        print(f"   {len(ids)} models total; NVIDIA/Nemotron ({len(nvidia)}):")
        for i in nvidia:
            print("    -", i)
        others = [i for i in ids if i not in nvidia and any(t in i.lower() for t in ("vl", "vision"))]
        if others:
            print("   Other vision-capable candidates:")
            for i in others:
                print("    -", i)
    else:
        ok = False
        print("   ERROR:", data)

    status, data = request(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {env.get('TAVILY_API_KEY', '')}"},
        body={"query": "PM Kisan scheme official", "include_domains": ["gov.in"], "max_results": 2},
    )
    print(f"== Tavily search -> {status}")
    if status == 200:
        for r in data.get("results", []):
            print("    -", r.get("url"))
    else:
        ok = False
        print("   ERROR:", data)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
