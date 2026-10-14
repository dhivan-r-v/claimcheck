"""The ClaimCheck agent: an async generator that yields progress events, then the result.

Stages
  read_image  Qwen3.8-27B (vision)    transcribe a screenshot
  understand  Nemotron 3.5 Lightning  language + checkable claims
  red_flags   deterministic           links and scam patterns (no model)
  plan        Nemotron 3 Nano         search queries per claim
  search      Tavily                  official / fact-check / news searches, in parallel
  read        Tavily Extract          full text of the best official pages
  weigh       Nemotron 3 Super        stance of every source, per claim, in parallel
  verdict     Nemotron 3 Ultra        final verdict with reasoning, in the sender's language
  guardrails  deterministic           never "VERIFIED" without official support / with critical flags
"""
import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator

import httpx

from . import config, prompts, redflags, search
from .llm import LLMError, TokenFactory

M = config.MODELS


def _event(stage: str, status: str, **data) -> dict:
    return {"type": "stage", "stage": stage, "status": status, **data}


class Pipeline:
    def __init__(self, client: httpx.AsyncClient):
        self.http = client
        self.llm = TokenFactory(client)

    async def run(self, text: str = "", image: bytes | None = None, mime: str = "image/png") -> AsyncIterator[dict]:
        t0 = time.monotonic()
        text = (text or "").strip()

        # 1. Screenshot -> text
        if image:
            yield _event("read_image", "running", model=M["vision"])
            url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
            ocr = await self.llm.chat(
                M["vision"],
                [
                    {"role": "system", "content": prompts.VISION},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Transcribe this image."},
                        {"type": "image_url", "image_url": {"url": url}},
                    ]},
                ],
                max_tokens=1500,
                timeout=90,
            )
            text = f"{text}\n\n{ocr.strip()}".strip()
            yield _event("read_image", "done", model=M["vision"], text=ocr.strip())

        if not text:
            yield {"type": "error", "message": "No text found in the message or image."}
            return

        # 2. Red flags are instant and model-free, so they show while the LLM reads the message.
        yield _event("understand", "running", model=M["understand"])
        flags = redflags.analyse(text)
        yield _event("red_flags", "done", flags=flags["flags"], urls=flags["urls"])
        info = await self.llm.chat_json(M["understand"], prompts.UNDERSTAND, text, max_tokens=1200)
        claims = (info.get("claims") or [])[: config.MAX_CLAIMS]
        for i, c in enumerate(claims, 1):
            c.setdefault("id", f"c{i}")
        yield _event("understand", "done", model=M["understand"], info={**info, "claims": claims})

        sources: list[dict] = []
        assessments: list[dict] = []
        if claims:
            # 4. Plan searches
            yield _event("plan", "running", model=M["plan"])
            allowed = sorted(config.OFFICIAL_DOMAINS)
            plan = await self.llm.chat_json(
                M["plan"],
                prompts.PLAN.format(domains=", ".join(allowed)),
                json.dumps([{k: c.get(k) for k in ("id", "claim_en", "entity", "keywords")} for c in claims]),
                max_tokens=1200,
            )
            plans = {p.get("id"): p for p in plan.get("plans", [])}
            yield _event("plan", "done", model=M["plan"], plans=list(plans.values()))

            # 5. Search: 3 Tavily searches per claim, all in parallel
            yield _event("search", "running", tool="Tavily Search")
            jobs, kinds = [], []
            for c in claims:
                p = plans.get(c["id"]) or {}
                base = c.get("entity") or c.get("claim_en", "")
                extra = [d for d in p.get("extra_domains", []) if d in config.OFFICIAL_DOMAINS]
                jobs += [
                    search.search(self.http, p.get("official") or base, depth="advanced",
                                  include_domains=["gov.in", "nic.in", *extra], max_results=4),
                    search.search(self.http, p.get("factcheck") or f"{base} fake fact check",
                                  include_domains=config.FACT_CHECK_DOMAINS, max_results=4),
                    search.search(self.http, p.get("news") or base, topic="news",
                                  time_range="year", max_results=3),
                ]
                kinds += [(c["id"], "official"), (c["id"], "factcheck"), (c["id"], "news")]
            results = await asyncio.gather(*jobs)

            seen: dict[str, dict] = {}
            for (cid, kind), hits in zip(kinds, results):
                for h in hits:
                    url = h.get("url")
                    if not url or search.is_junk(h.get("content")):
                        continue
                    if url not in seen:
                        host = search.domain(url)
                        seen[url] = {
                            "n": len(seen) + 1, "url": url, "title": h.get("title", ""), "domain": host,
                            "kind": "official" if search.is_official(host) else kind,
                            "snippet": (h.get("content") or "")[:700], "claims": [],
                        }
                    if cid not in seen[url]["claims"]:
                        seen[url]["claims"].append(cid)
            sources = list(seen.values())
            yield _event("search", "done", tool="Tavily Search", count=len(sources),
                         sources=[{k: s[k] for k in ("n", "url", "title", "domain", "kind")} for s in sources])

            # 6. Read in full: official links in the message itself + the top official result per claim
            linked = [u if u.lower().startswith("http") else f"https://{u}" for u in flags["official_urls"]]
            linked = [u for u in linked if u not in seen][:2]
            to_read = list(linked)
            for c in claims:
                off = [s for s in sources if c["id"] in s["claims"] and s["kind"] == "official"]
                if off and off[0]["url"] not in to_read:
                    to_read.append(off[0]["url"])
            if to_read:
                yield _event("read", "running", tool="Tavily Extract", urls=to_read)
                pages = await search.extract(self.http, to_read)
                all_kws = [k for c in claims for k in c.get("keywords", [])]
                for u in linked:
                    if not search.is_junk(pages.get(u)):
                        sources.append({
                            "n": len(sources) + 1, "url": u, "title": "Official link in the message",
                            "domain": search.domain(u), "kind": "official", "snippet": "",
                            "claims": [c["id"] for c in claims],
                        })
                for s in sources:
                    if s["url"] in pages and not search.is_junk(pages[s["url"]]):
                        kws = [k for c in claims if c["id"] in s["claims"] for k in c.get("keywords", [])]
                        s["page"] = search.relevant_passages(pages[s["url"]], kws or all_kws)
                read = sum(1 for s in sources if s.get("page"))
                yield _event("read", "done", tool="Tavily Extract", read=read)

            # 7. Weigh evidence per claim, in parallel
            yield _event("weigh", "running", model=M["assess"])
            assessments = await asyncio.gather(*(self._assess(c, sources) for c in claims))
            yield _event("weigh", "done", model=M["assess"], assessments=assessments)

        # 8. Verdict
        yield _event("verdict", "running", model=M["verdict"])
        verdict, used = await self._verdict(text, info, claims, assessments, sources, flags)
        verdict = apply_guardrails(verdict, flags, assessments, sources)
        yield _event("verdict", "done", model=used)

        yield {
            "type": "result",
            "verdict": verdict,
            "reply_language": info.get("reply_language", "English"),
            "message_text": text,
            "claims": claims,
            "assessments": assessments,
            "red_flags": flags,
            "sources": [{k: s[k] for k in ("n", "url", "title", "domain", "kind")} for s in sources],
            "models": {**M, "verdict_used": used},
            "seconds": round(time.monotonic() - t0, 1),
        }

    async def _assess(self, claim: dict, sources: list[dict]) -> dict:
        mine = [s for s in sources if claim["id"] in s["claims"]]
        if not mine:
            return {"claim_id": claim["id"], "stances": [], "finding_en": "No sources found."}
        evidence = "\n\n".join(
            f"[{s['n']}] ({s['kind']}) {s['domain']} — {s['title']}\n{s.get('page') or s['snippet']}"
            for s in mine
        )
        try:
            out = await self.llm.chat_json(
                M["assess"], prompts.ASSESS,
                f"CLAIM ({claim['id']}): {claim.get('claim_en')}\n\nSOURCES:\n{evidence}",
                max_tokens=1500,
            )
        except (LLMError, ValueError):
            return {"claim_id": claim["id"], "stances": [], "finding_en": "Could not assess sources."}
        valid = {s["n"] for s in mine}
        out["claim_id"] = claim["id"]
        out["stances"] = [s for s in out.get("stances", []) if s.get("n") in valid]
        return out

    async def _verdict(self, text, info, claims, assessments, sources, flags) -> tuple[dict, str]:
        stance_by_n = {
            st["n"]: st for a in assessments for st in a.get("stances", []) if st.get("stance") != "neutral"
        }
        payload = {
            "message": text[:3000],
            "summary": info.get("summary_en"),
            "requested_actions": info.get("requested_actions", []),
            "claims": [{k: c.get(k) for k in ("id", "claim_en", "entity")} for c in claims],
            "assessments": assessments,
            "sources": [
                {"n": s["n"], "domain": s["domain"], "kind": s["kind"], "title": s["title"],
                 **({"stance": stance_by_n[s["n"]]} if s["n"] in stance_by_n else {})}
                for s in sources
            ],
            "red_flags": flags["flags"],
        }
        system = prompts.VERDICT.format(reply_language=info.get("reply_language", "English"))
        user = json.dumps(payload, ensure_ascii=False)
        try:
            return await self.llm.chat_json(M["verdict"], system, user, think=True,
                                            max_tokens=8000, timeout=150), M["verdict"]
        except (LLMError, ValueError):
            return await self.llm.chat_json(M["verdict_fallback"], system, user, think=True,
                                            max_tokens=6000, timeout=120), M["verdict_fallback"]


def apply_guardrails(verdict: dict, flags: dict, assessments: list[dict], sources: list[dict]) -> dict:
    """Hard rules the model cannot override."""
    v = str(verdict.get("verdict", "UNVERIFIED")).upper()
    if v not in {"SCAM", "VERIFIED", "UNVERIFIED"}:
        v = "UNVERIFIED"
    official = {s["n"] for s in sources if s["kind"] == "official"}
    official_support = any(
        st.get("stance") == "supports" and st.get("n") in official
        for a in assessments for st in a.get("stances", [])
    )
    notes = []
    if flags["critical"] and v != "SCAM":
        notes.append(f"Changed from {v} to SCAM: the message contains critical scam signals.")
        v = "SCAM"
    elif v == "VERIFIED" and not official_support:
        notes.append("Changed from VERIFIED to UNVERIFIED: no official source confirmed the claim.")
        v = "UNVERIFIED"
    return {**verdict, "verdict": v, "guardrail_notes": notes}
