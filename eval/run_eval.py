"""Run ClaimCheck over eval/dataset.jsonl and report accuracy.

Usage:
  python eval/run_eval.py                 # full set
  python eval/run_eval.py --ids s01,g01   # a few items
  python eval/run_eval.py --limit 5

Tavily responses are cached in eval/.search_cache, so reruns (e.g. after a prompt change) only
spend Token Factory credits. Writes eval/results/run-<time>.json and eval/RESULTS.md.
"""
import argparse
import asyncio
import json
import mimetypes
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
os.environ.setdefault("SEARCH_CACHE_DIR", str(EVAL / ".search_cache"))
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from claimcheck import config  # noqa: E402
from claimcheck.pipeline import Pipeline  # noqa: E402

LABELS = ["SCAM", "VERIFIED", "UNVERIFIED"]


async def run_one(pipe: Pipeline, item: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        img = mime = None
        if item.get("image"):
            path = ROOT / item["image"]
            img, mime = path.read_bytes(), mimetypes.guess_type(path)[0]
        t0 = time.monotonic()
        out = {**item, "predicted": None, "error": None}
        try:
            async for ev in pipe.run(item["text"], img, mime or "image/png"):
                if ev["type"] == "result":
                    v = ev["verdict"]
                    out.update(
                        predicted=v["verdict"],
                        headline=v.get("headline_en"),
                        reply_language=ev["reply_language"],
                        reply_local=v.get("reply_local"),
                        guardrail_notes=v.get("guardrail_notes", []),
                        flags=[f["code"] for f in ev["red_flags"]["flags"]],
                        n_claims=len(ev["claims"]),
                        n_sources=len(ev["sources"]),
                        verdict_model=ev["models"]["verdict_used"],
                        fp_level=ev["fingerprint"]["level"],
                        fp_score=ev["fingerprint"]["score"],
                        fp_tactics=ev["fingerprint"]["active"],
                    )
                elif ev["type"] == "error":
                    out["error"] = ev["message"]
        except Exception as e:  # keep going; one failure shouldn't sink the run
            out["error"] = f"{type(e).__name__}: {e}"
        out["seconds"] = round(time.monotonic() - t0, 1)
        mark = "OK " if out["predicted"] == item["expected"] else "XX "
        print(f"{mark}{item['id']:4} expected {item['expected']:10} got {str(out['predicted']):10} "
              f"{out['seconds']:5.1f}s  {out.get('headline') or out['error'] or ''}"[:150], flush=True)
        return out


def metrics(rows: list[dict]) -> dict:
    done = [r for r in rows if r["predicted"]]
    scams = [r for r in done if r["expected"] == "SCAM"]
    genuine = [r for r in done if r["expected"] == "VERIFIED"]
    confusion = {e: Counter(r["predicted"] for r in done if r["expected"] == e) for e in ("SCAM", "VERIFIED")}
    secs = [r["seconds"] for r in done]

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    zero_day = [r for r in scams if r["category"] == "zero_day"]
    fp_flagged = lambda r: r.get("fp_level") in ("high", "medium")  # noqa: E731
    return {
        "zero_day_caught": f"{sum(r['predicted'] == 'SCAM' for r in zero_day)}/{len(zero_day)}",
        # The fingerprint alone, with no search at all, used as a classifier.
        "fp_scams_flagged": pct(sum(fp_flagged(r) for r in scams), len(scams)),
        "fp_genuine_flagged": f"{sum(fp_flagged(r) for r in genuine)}/{len(genuine)}",
        "fp_genuine_high": sum(r.get("fp_level") == "high" for r in genuine),
        "n": len(rows),
        "errors": len(rows) - len(done),
        "accuracy": pct(sum(r["predicted"] == r["expected"] for r in done), len(done)),
        "scam_caught": pct(sum(r["predicted"] == "SCAM" for r in scams), len(scams)),
        # The number that matters most: scams the app called safe.
        "scams_marked_verified": sum(r["predicted"] == "VERIFIED" for r in scams),
        "scams_flagged_unsafe": pct(sum(r["predicted"] != "VERIFIED" for r in scams), len(scams)),
        "genuine_verified": pct(sum(r["predicted"] == "VERIFIED" for r in genuine), len(genuine)),
        "genuine_marked_scam": sum(r["predicted"] == "SCAM" for r in genuine),
        "n_scam": len(scams),
        "n_genuine": len(genuine),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "latency_median": round(statistics.median(secs), 1) if secs else None,
        "latency_p90": round(sorted(secs)[int(0.9 * (len(secs) - 1))], 1) if secs else None,
        "by_lang": {
            lang: f"{sum(r['predicted'] == r['expected'] for r in done if r['lang'] == lang)}/"
                  f"{sum(1 for r in done if r['lang'] == lang)}"
            for lang in sorted({r["lang"] for r in done})
        },
    }


def write_report(m: dict, rows: list[dict], stamp: str) -> str:
    conf = m["confusion"]
    lines = [
        "# ClaimCheck evaluation",
        "",
        f"Run {stamp} on {m['n']} messages ({m['n_scam']} scams or false claims, {m['n_genuine']} genuine) "
        f"from [`dataset.jsonl`](dataset.jsonl). Models: {', '.join(sorted(set(config.MODELS.values())))}.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| **Scams marked VERIFIED (called safe)** | **{m['scams_marked_verified']} of {m['n_scam']}** |",
        f"| Scams flagged as unsafe (SCAM or UNVERIFIED) | {m['scams_flagged_unsafe']}% |",
        f"| Scams labelled exactly SCAM | {m['scam_caught']}% |",
        f"| Genuine messages VERIFIED | {m['genuine_verified']}% |",
        f"| Genuine messages wrongly called SCAM | {m['genuine_marked_scam']} of {m['n_genuine']} |",
        f"| Exact-label accuracy | {m['accuracy']}% |",
        f"| **Zero-day scams caught** (invented, no search history) | **{m['zero_day_caught']}** |",
        f"| Fingerprint alone (no search): scams flagged medium/high | {m['fp_scams_flagged']}% |",
        f"| Fingerprint alone: genuine messages flagged medium/high | {m['fp_genuine_flagged']} |",
        f"| Median / p90 time per check | {m['latency_median']}s / {m['latency_p90']}s |",
        f"| Runs that errored | {m['errors']} |",
        "",
        "**Confusion matrix** (rows: expected, columns: predicted)",
        "",
        "| | SCAM | VERIFIED | UNVERIFIED |",
        "|---|---|---|---|",
        *[f"| {e} | " + " | ".join(str(conf.get(e, {}).get(p, 0)) for p in LABELS) + " |" for e in ("SCAM", "VERIFIED")],
        "",
        "**Correct by language:** " + ", ".join(f"{k} {v}" for k, v in m["by_lang"].items()),
        "",
        "## Misses",
        "",
        "| id | lang | expected | got | fingerprint | headline |",
        "|---|---|---|---|---|---|",
        *[f"| {r['id']} | {r['lang']} | {r['expected']} | {r['predicted'] or 'error'} | "
          f"{r.get('fp_level', '-')} {r.get('fp_score', '')} | "
          f"{(r.get('headline') or r.get('error') or '').replace('|', '/')} |"
          for r in rows if r["predicted"] != r["expected"]],
    ]
    return "\n".join(lines) + "\n"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated item ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--category", help="only items of this category, e.g. zero_day")
    ap.add_argument("--print-report", action="store_true", help="print the markdown report (for job logs)")
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    items = [json.loads(l) for l in (EVAL / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.ids:
        wanted = set(args.ids.split(","))
        items = [i for i in items if i["id"] in wanted]
    if args.category:
        items = [i for i in items if i["category"] == args.category]
    if args.limit:
        items = items[: args.limit]

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        pipe = Pipeline(client)
        rows = await asyncio.gather(*(run_one(pipe, i, sem) for i in items))

    m = metrics(rows)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("\n" + json.dumps(m, indent=2))

    results = EVAL / "results"
    results.mkdir(exist_ok=True)
    (results / f"run-{datetime.now():%Y%m%d-%H%M%S}.json").write_text(
        json.dumps({"metrics": m, "models": config.MODELS, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.print_report or os.getenv("NEBIUS_JOB") or args.category:
        print("
" + write_report(m, rows, stamp))
    if not args.ids and not args.limit and not args.category:
        (EVAL / "RESULTS.md").write_text(write_report(m, rows, stamp), encoding="utf-8")
        print("wrote eval/RESULTS.md")


if __name__ == "__main__":
    asyncio.run(main())
