"""Run the pipeline from the command line and print each stage.

Usage:
  python scripts/try_pipeline.py "message text"
  python scripts/try_pipeline.py --image path/to/screenshot.png
"""
import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claimcheck.pipeline import Pipeline  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--image")
    ap.add_argument("--json", action="store_true", help="print the full result JSON")
    args = ap.parse_args()

    img, mime = None, "image/png"
    if args.image:
        img = Path(args.image).read_bytes()
        mime = mimetypes.guess_type(args.image)[0] or mime

    async with httpx.AsyncClient() as client:
        async for ev in Pipeline(client).run(args.text, img, mime):
            if ev["type"] == "stage":
                who = ev.get("model") or ev.get("tool") or "rules"
                extra = ""
                if ev["stage"] == "red_flags":
                    extra = " | " + "; ".join(f"{f['severity']}: {f['label']}" for f in ev["flags"])
                elif ev["stage"] == "search" and ev["status"] == "done":
                    extra = f" | {ev['count']} sources"
                elif ev["stage"] == "understand" and ev["status"] == "done":
                    info = ev["info"]
                    extra = f" | {info.get('reply_language')} | " + "; ".join(c["claim_en"] for c in info["claims"])
                print(f"[{ev['status']:7}] {ev['stage']:10} {who}{extra}")
            elif ev["type"] == "result":
                v = ev["verdict"]
                print(f"\n=== {v['verdict']} — {v.get('headline_en')}  ({ev['seconds']}s)")
                print(v.get("explanation_en"))
                print("\nReply:", v.get("reply_local"))
                for note in v.get("guardrail_notes", []):
                    print("Guardrail:", note)
                for s in ev["sources"]:
                    print(f"  [{s['n']}] {s['kind']:9} {s['url']}")
                if args.json:
                    print(json.dumps(ev, ensure_ascii=False, indent=2))
            else:
                print("ERROR:", ev)


if __name__ == "__main__":
    asyncio.run(main())
