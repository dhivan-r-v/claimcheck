import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimcheck import config, telegram
from claimcheck.store import results

RESULT = {
    "type": "result",
    "verdict": {
        "verdict": "SCAM",
        "headline_en": "Fake <PM Kisan> link",
        "explanation_en": "The link is not official [1].",
        "reply_local": "Ye message scam hai.",
        "claims": [{"id": "c1", "status": "false", "sources": [1]}],
        "advice_en": ["Don't click the link.", "Check pmkisan.gov.in", "Third tip"],
    },
    "red_flags": {"flags": [{"code": "fake_gov_domain", "severity": "critical", "label": "Fake gov link", "evidence": "x"}]},
    "assessments": [{"claim_id": "c1", "stances": [{"n": 2, "stance": "contradicts"}]}],
    "sources": [
        {"n": 1, "url": "https://pib.gov.in/a?x=1&y=2", "title": "PIB", "domain": "pib.gov.in", "kind": "official"},
        {"n": 2, "url": "https://factly.in/b", "title": "Factly", "domain": "factly.in", "kind": "factcheck"},
        {"n": 3, "url": "https://example.com/c", "title": "Other", "domain": "example.com", "kind": "news"},
    ],
}


class FakePipeline:
    def __init__(self):
        self.calls = []

    async def run(self, text, image=None, mime="image/png"):
        self.calls.append(text)
        yield {"type": "stage", "stage": "understand", "status": "running"}
        yield {"type": "stage", "stage": "understand", "status": "done"}
        yield RESULT


@pytest.fixture
def bot(monkeypatch):
    sent = []

    async def fake_call(client, method, **params):
        sent.append((method, params))
        return {"ok": True, "result": {"message_id": 99}}

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setattr(telegram, "_call", fake_call)
    results._data.clear()
    return sent


def run(msg, pipeline):
    asyncio.run(telegram.handle_message(None, pipeline, msg))


def test_format_result_escapes_and_cites():
    out = telegram.format_result(RESULT)
    assert out.startswith("🚫 <b>SCAM / FALSE</b>")
    assert "Fake &lt;PM Kisan&gt; link" in out          # HTML escaped
    assert "Ye message scam hai." in out and "<i>The link is not official [1].</i>" in out
    assert 'href="https://pib.gov.in/a?x=1&amp;y=2"' in out
    assert "factly.in" in out and "example.com" not in out  # only cited/decisive sources
    assert out.count("👉") == 2


def test_private_message_is_checked_and_status_edited(bot):
    pipe = FakePipeline()
    run({"message_id": 1, "chat": {"id": 7, "type": "private"}, "from": {"id": 7}, "text": "PM Kisan 12000 milenge"}, pipe)
    assert pipe.calls == ["PM Kisan 12000 milenge"]
    methods = [m for m, _ in bot]
    assert methods[0] == "sendMessage" and methods[-1] == "editMessageText"
    assert bot[-1][1]["text"].startswith("🚫")


def test_repeat_message_uses_cache(bot):
    pipe = FakePipeline()
    msg = {"message_id": 1, "chat": {"id": 7, "type": "private"}, "from": {"id": 7}, "text": "same forward"}
    run(msg, pipe)
    run(msg, pipe)
    assert len(pipe.calls) == 1


def test_group_ignores_plain_messages_but_checks_replies(bot):
    pipe = FakePipeline()
    group = {"id": -5, "type": "group"}
    run({"message_id": 1, "chat": group, "from": {"id": 8}, "text": "hello everyone"}, pipe)
    assert pipe.calls == [] and bot == []

    forward = {"message_id": 2, "chat": group, "text": "Free laptop yojana, apply now"}
    run({"message_id": 3, "chat": group, "from": {"id": 8}, "text": "/check@ClaimCheckBot",
         "reply_to_message": forward}, pipe)
    assert pipe.calls == ["Free laptop yojana, apply now"]
    assert bot[0][1]["reply_to_message_id"] == 2


def test_help_command(bot):
    run({"message_id": 1, "chat": {"id": 7, "type": "private"}, "text": "/start"}, FakePipeline())
    assert bot[0][0] == "sendMessage" and "ClaimCheck" in bot[0][1]["text"]


def test_webhook_rejects_wrong_secret(bot):
    app = FastAPI()
    app.include_router(telegram.router)
    with TestClient(app) as client:
        r = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"})
        assert r.status_code == 403
        r = client.post("/telegram/webhook", json={"update_id": 1})
        assert r.status_code == 403


def test_webhook_secret_is_telegram_safe(bot, monkeypatch):
    import re
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", "a+b/c=d==")  # Render-style generated value
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", telegram._secret())


def test_webhook_accepts_derived_secret(bot):
    app = FastAPI()
    app.include_router(telegram.router)
    app.state.http, app.state.pipeline = None, FakePipeline()
    with TestClient(app) as client:
        r = client.post("/telegram/webhook", json={"update_id": 42},
                        headers={"X-Telegram-Bot-Api-Secret-Token": telegram._secret()})
        assert r.status_code == 200


def test_scam_links_are_defanged_but_official_links_kept():
    out = telegram.defang("Don't open http://pw5.in or pmkisan-gov.in.apply-now.xyz/reg; use https://pmkisan.gov.in")
    assert "hxxp://pw5[.]in" in out
    assert "pmkisan-gov[.]in[.]apply-now[.]xyz/reg" in out
    assert "https://pmkisan.gov.in" in out


def test_format_result_defangs_text_but_not_source_links():
    ev = {**RESULT, "verdict": {**RESULT["verdict"], "explanation_en": "The link http://pw5.in is fake [1]."}}
    out = telegram.format_result(ev)
    assert "hxxp://pw5[.]in" in out and "http://pw5.in" not in out
    assert 'href="https://pib.gov.in/a?x=1&amp;y=2"' in out


def test_format_result_shows_fingerprint_with_defanged_evidence():
    from claimcheck import fingerprint
    fp = fingerprint.build({"tactics": {"credential_request": {"score": 3, "evidence": "send OTP to http://pw5.in"},
                                        "authority": {"score": 3, "evidence": "Ministry of Digital Welfare"},
                                        "reward": {"score": 2, "evidence": "Rs 6,250"}},
                            "impersonates": "Ministry of Digital Welfare"}, [])
    out = telegram.format_result({**RESULT, "fingerprint": fp})
    assert "<b>Manipulation: HIGH" in out and "Pretends to be: Ministry of Digital Welfare" in out
    assert "hxxp://pw5[.]in" in out and "Warning signs" not in out


def test_group_check_with_quote_only(bot):
    # Some clients send only the quoted part of the replied-to message.
    pipe = FakePipeline()
    run({"message_id": 5, "chat": {"id": -5, "type": "supergroup"}, "from": {"id": 8}, "text": "/check",
         "quote": {"text": "Free laptop yojana, apply now", "position": 0}}, pipe)
    assert pipe.calls == ["Free laptop yojana, apply now"]


def test_group_check_with_external_reply_photo_caption(bot):
    pipe = FakePipeline()
    run({"message_id": 6, "chat": {"id": -5, "type": "group"}, "from": {"id": 8}, "text": "/check",
         "external_reply": {"caption": "Rs 6250 bonus, send OTP"}}, pipe)
    assert pipe.calls == ["Rs 6250 bonus, send OTP"]
    assert bot[0][1]["reply_to_message_id"] == 6  # no id on external replies: answer the /check itself


def test_handler_crash_is_reported_to_user(bot, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(telegram, "handle_message", boom)
    asyncio.run(telegram._handle_safely(None, None, {"chat": {"id": 7, "type": "private"}, "message_id": 1}))
    assert bot[-1][0] == "sendMessage" and "went wrong" in bot[-1][1]["text"]
