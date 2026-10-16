"""Telegram bot, served by the same app through a webhook.

Private chat: send or forward any message or screenshot and get a verdict.
Groups: reply /check to a forwarded message. Everything else in groups is ignored.

Telegram calls POST /telegram/webhook with a secret header; we acknowledge at once and run
the check in a background task, editing one status message as the pipeline progresses.
"""
import asyncio
import hashlib
import html
import logging
import re
import secrets
from collections import deque

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from . import config, redflags, search
from .llm import LLMError
from .store import cache_key, limiter, results

router = APIRouter()
log = logging.getLogger("claimcheck.telegram")
API = "https://api.telegram.org"

STAGES = {
    "read_image": "Reading the screenshot",
    "understand": "Understanding the message",
    "fingerprint": "Analysing manipulation tactics",
    "plan": "Planning the searches",
    "search": "Searching official sites & fact-checkers",
    "read": "Reading official pages",
    "weigh": "Weighing the evidence",
    "verdict": "Reaching a verdict",
}
BADGE = {
    "SCAM": "🚫 <b>SCAM / FALSE</b>",
    "VERIFIED": "✅ <b>VERIFIED</b>",
    "UNVERIFIED": "⚠️ <b>UNVERIFIED</b>, be careful",
}
HELP = (
    "👋 <b>ClaimCheck</b> checks suspicious forwards before you click, pay or share.\n\n"
    "• <b>Forward me</b> any WhatsApp/SMS message, or send a <b>screenshot</b>. Any language is fine.\n"
    "• In a <b>group</b>, reply <code>/check</code> to the message you want checked.\n\n"
    "I search official .gov.in sites and fact-checkers, then reply SCAM, VERIFIED or UNVERIFIED with sources.\n\n"
    "कोई भी संदेश या स्क्रीनशॉट भेजें, मैं जाँच कर बताऊँगा कि वह सच है या धोखा।"
)

_tasks: set[asyncio.Task] = set()
_seen_updates: deque[int] = deque(maxlen=500)  # Telegram re-sends updates it thinks we missed


# Outcome of the last setWebhook call, shown on /api/health (never includes secrets).
webhook_status: dict = {"registered": False, "error": None}


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _secret() -> str:
    """Telegram only accepts [A-Za-z0-9_-] in secret tokens, so hash whatever secret we were given.
    Falls back to the bot token so the webhook is always protected."""
    seed = config.TELEGRAM_WEBHOOK_SECRET or config.TELEGRAM_BOT_TOKEN
    return hashlib.sha256(f"claimcheck-webhook:{seed}".encode()).hexdigest() if seed else ""


async def _call(client: httpx.AsyncClient, method: str, **params) -> dict:
    try:
        r = await client.post(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=30)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("telegram %s failed: %s", method, type(e).__name__)
        return {"ok": False}
    if not data.get("ok"):
        log.warning("telegram %s failed: %s", method, data.get("description"))
    return data


async def register_webhook(client: httpx.AsyncClient) -> None:
    if not enabled():
        return
    if not config.PUBLIC_URL:
        webhook_status.update(registered=False, error="no PUBLIC_URL / RENDER_EXTERNAL_URL set")
        log.warning("telegram webhook not registered: %s", webhook_status["error"])
        return
    res = await _call(
        client, "setWebhook",
        url=f"{config.PUBLIC_URL}/telegram/webhook",
        secret_token=_secret(),
        allowed_updates=["message"],
    )
    webhook_status.update(registered=bool(res.get("ok")), error=None if res.get("ok") else res.get("description", "failed"))
    log.info("telegram webhook registered=%s error=%s", webhook_status["registered"], webhook_status["error"])
    await _call(client, "setMyCommands", commands=[
        {"command": "check", "description": "Check a message (reply to it in groups)"},
        {"command": "help", "description": "How to use ClaimCheck"},
    ])


@router.post("/telegram/webhook", include_in_schema=False)
async def webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(None)):
    secret = _secret()
    if not (enabled() and secret and secrets.compare_digest(x_telegram_bot_api_secret_token or "", secret)):
        raise HTTPException(403)
    update = await request.json()
    uid = update.get("update_id")
    if uid in _seen_updates:
        return {"ok": True}
    _seen_updates.append(uid)
    if msg := update.get("message"):
        task = asyncio.create_task(_handle_safely(request.app.state.http, request.app.state.pipeline, msg))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"ok": True}


async def _handle_safely(client: httpx.AsyncClient, pipeline, msg: dict) -> None:
    """A background task's exception is otherwise lost silently: log it and tell the user."""
    try:
        await handle_message(client, pipeline, msg)
    except Exception:
        log.exception("telegram handler crashed: chat=%s keys=%s", msg.get("chat", {}).get("type"), sorted(msg))
        await _call(client, "sendMessage", chat_id=msg["chat"]["id"],
                    text="Sorry, something went wrong while checking. Please try again.")


def _command(text: str) -> str | None:
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lower()


async def handle_message(client: httpx.AsyncClient, pipeline, msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    private = msg["chat"].get("type") == "private"
    own_text = msg.get("text") or msg.get("caption") or ""
    cmd = _command(own_text)

    if cmd in {"/start", "/help"}:
        await _call(client, "sendMessage", chat_id=chat_id, text=HELP, parse_mode="HTML")
        return

    if cmd == "/check":
        # Telegram can deliver the replied-to message as reply_to_message, as external_reply
        # (another chat), or only as a quote of the selected part.
        target = msg.get("reply_to_message") or msg.get("external_reply")
        quote = (msg.get("quote") or {}).get("text") or ""
        rest = own_text.split(maxsplit=1)[1] if len(own_text.split(maxsplit=1)) > 1 else ""
        if target is not None:
            body = target.get("text") or target.get("caption") or quote
        elif quote:
            target, body = msg, quote
        elif rest:
            target, body = msg, rest  # "/check <text>"
        else:
            # Structure only (never content), to diagnose clients that send replies differently.
            log.warning("telegram /check without a reply: chat=%s keys=%s",
                        msg["chat"].get("type"), sorted(msg))
            await _call(client, "sendMessage", chat_id=chat_id, parse_mode="HTML",
                        text="Reply <code>/check</code> to the message you want me to check.")
            return
        if "message_id" not in target:
            target = {**target, "message_id": msg["message_id"]}
    elif private:
        target, body = msg, own_text
    else:
        return  # groups: only act on /check

    image = await _download_photo(client, target)
    body = body.strip()[: config.MAX_TEXT_CHARS]
    if not body and image is None:
        await _call(client, "sendMessage", chat_id=chat_id, reply_to_message_id=target["message_id"],
                    text="Send me the text of a message or a screenshot to check.")
        return

    key = cache_key(body, image)
    cached = results.get(key)
    user = (msg.get("from") or {}).get("id", chat_id)
    if cached is None and limiter.limited(f"tg:{user}"):
        await _call(client, "sendMessage", chat_id=chat_id, reply_to_message_id=target["message_id"],
                    text="You've reached the hourly limit of checks. Please try again in an hour.")
        return

    sent = await _call(client, "sendMessage", chat_id=chat_id, reply_to_message_id=target["message_id"],
                       text="🔎 Checking… this takes about 20 seconds.")
    status_id = (sent.get("result") or {}).get("message_id")

    async def show(text: str) -> None:
        if status_id:
            await _call(client, "editMessageText", chat_id=chat_id, message_id=status_id, text=text,
                        parse_mode="HTML", disable_web_page_preview=True)
        else:
            await _call(client, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                        disable_web_page_preview=True)

    if cached is not None:
        await show(format_result(cached))
        return

    done: list[str] = []
    try:
        async for ev in pipeline.run(body, image, "image/jpeg"):
            if ev["type"] == "stage" and ev["stage"] in STAGES:
                if ev["status"] == "done":
                    done.append(STAGES[ev["stage"]])
                else:
                    await show("🔎 <b>Checking…</b>\n" + "".join(f"✓ {s}\n" for s in done)
                               + f"⏳ {STAGES[ev['stage']]}…")
            elif ev["type"] == "result":
                results.put(key, ev)
                await show(format_result(ev))
            elif ev["type"] == "error":
                await show(f"Sorry, I couldn't check this: {html.escape(ev['message'])}")
    except (LLMError, httpx.HTTPError, ValueError) as e:
        log.exception("telegram check failed: %s", e)
        await show("Sorry, something went wrong while checking. Please try again.")


async def _download_photo(client: httpx.AsyncClient, msg: dict) -> bytes | None:
    file_id = None
    if msg.get("photo"):
        best = max(msg["photo"], key=lambda p: p.get("file_size", 0) or p.get("width", 0))
        if (best.get("file_size") or 0) <= config.MAX_IMAGE_BYTES:
            file_id = best["file_id"]
    elif (doc := msg.get("document")) and str(doc.get("mime_type", "")).startswith("image/"):
        if (doc.get("file_size") or 0) <= config.MAX_IMAGE_BYTES:
            file_id = doc["file_id"]
    if not file_id:
        return None
    info = await _call(client, "getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        return None
    try:
        r = await client.get(f"{API}/file/bot{config.TELEGRAM_BOT_TOKEN}/{path}", timeout=30)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    return r.content


_PHONE = re.compile(r"(?<![\w/=.])((?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|\+\d{1,3}[\s-]?\d{2,4}(?:[\s-]?\d{3,4}){2})(?![\w/])")


def defang(text: str) -> str:
    """Make non-official links untappable (hxxp://pw5[.]in). Telegram auto-links any URL in a
    message, and a scam warning must never hand the reader a working scam link."""
    for url in redflags.find_urls(text):
        if search.is_official(redflags._host(url)):
            continue
        safe = re.sub(r"^http", "hxxp", url, flags=re.I).replace(".", "[.]")
        text = text.replace(url, safe)
    return text


def format_result(ev: dict) -> str:
    """The verdict as a Telegram HTML message (<= 4096 chars)."""
    v = ev["verdict"]

    def e(s: str) -> str:
        # Code-format phone numbers: Telegram makes plain ones tappable, i.e. one tap to call the scammer.
        return _PHONE.sub(r"<code>\1</code>", html.escape(defang(s)))
    lines = [BADGE.get(v.get("verdict"), BADGE["UNVERIFIED"]), f"<b>{e(v.get('headline_en') or '')}</b>", ""]
    # Clip before escaping so the 4096-char limit is never hit mid-tag.
    local, english = (v.get("reply_local") or "")[:1500], (v.get("explanation_en") or "")[:1200]
    lines.append(e(local or english))
    if local and english and local != english:
        lines += ["", f"<i>{e(english)}</i>"]

    fp = ev.get("fingerprint")
    if fp and fp.get("active"):
        lines += ["", f"<b>Manipulation: {e(fp['level'].upper())} ({fp['score']}/100)</b>"]
        if fp.get("impersonates"):
            lines.append(f"Pretends to be: {e(fp['impersonates'][:80])}")
        for k in fp["active"][:4]:
            t = fp["tactics"][k]
            quote = f" — <i>“{e(t['evidence'][:80])}”</i>" if t.get("evidence") else ""
            lines.append(f"• {e(t['label'])}{quote}")
    else:
        flags = ev.get("red_flags", {}).get("flags", [])[:3]
        if flags:
            lines += ["", "<b>Warning signs</b>"] + [f"• {e(f['label'])}" for f in flags]

    decisive = {
        st["n"] for a in ev.get("assessments", []) for st in a.get("stances", [])
        if st.get("stance") in {"supports", "contradicts"}
    }
    cited = {n for c in v.get("claims", []) for n in c.get("sources", [])}
    sources = [s for s in ev.get("sources", []) if s["n"] in (cited | decisive)]
    sources.sort(key=lambda s: (s["kind"] != "official", s["kind"] != "factcheck", s["n"]))
    if sources:
        lines += ["", "<b>Sources</b>"] + [
            # Source links are our own search results, so they stay tappable.
            f"[{s['n']}] <a href=\"{html.escape(s['url'], quote=True)}\">{html.escape(s['domain'])}</a>"
            for s in sources[:4]
        ]

    advice = (v.get("advice_en") or [])[:2]
    if advice:
        lines += [""] + [f"👉 {e(a)}" for a in advice]

    footer = "Checked with NVIDIA Nemotron on Nebius Token Factory + Tavily"
    if config.PUBLIC_URL:
        footer += f' · <a href="{html.escape(config.PUBLIC_URL, quote=True)}">ClaimCheck</a>'
    lines += ["", f"<i>{footer}</i>"]

    text = "\n".join(lines)
    return text if len(text) <= 4096 else text[:4000] + "…"
