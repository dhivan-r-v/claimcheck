from claimcheck.pipeline import apply_guardrails
from claimcheck.redflags import analyse, find_urls


def codes(text):
    return {f["code"] for f in analyse(text)["flags"]}


def test_fake_gov_domain():
    assert "fake_gov_domain" in codes("Apply now: pmkisan.gov.in.verify-kyc.xyz/apply")


def test_lookalike_domain_and_risky_tld():
    c = codes("PM Kisan 5000 milega, register karo pmkisan-yojana.online")
    assert {"lookalike_domain", "risky_tld"} <= c


def test_official_links_pass():
    r = analyse("Check status on https://pmkisan.gov.in and https://www.rbi.org.in")
    assert r["flags"] == []
    assert len(r["official_urls"]) == 2


def test_otp_and_urgency_hinglish():
    c = codes("Aapka bijli connection aaj raat cut ho jayega. Turant OTP bhejo is number pe")
    assert {"asks_otp_pin", "threat", "urgency"} <= c


def test_tamil_urgency():
    assert "urgency" in codes("உடனே இந்த லிங்கை கிளிக் செய்யவும்")


def test_tamil_disconnection_threat():
    assert "threat" in codes("இன்றிரவு 9.30 மணிக்கு உங்கள் மின் இணைப்பு துண்டிக்கப்படும்")


def test_hindi_account_block_threat():
    assert {"threat", "urgency"} <= codes("आपका SBI खाता आज बंद हो जाएगा। तुरंत PAN अपडेट करें")


def test_apk_and_shortener():
    assert {"apk_download", "shortener"} <= codes("Download SBI-Rewards.apk from bit.ly/sbi-pts")


def test_no_false_positive_on_amounts():
    assert find_urls("Rs.5000 milenge, e.g. next month") == []


def test_guardrail_critical_forces_scam():
    v = apply_guardrails({"verdict": "VERIFIED"}, {"critical": True}, [], [])
    assert v["verdict"] == "SCAM" and v["guardrail_notes"]


def test_guardrail_verified_needs_official_support():
    sources = [{"n": 1, "kind": "news"}]
    assessments = [{"stances": [{"n": 1, "stance": "supports"}]}]
    v = apply_guardrails({"verdict": "VERIFIED"}, {"critical": False}, assessments, sources)
    assert v["verdict"] == "UNVERIFIED"

    sources = [{"n": 1, "kind": "official"}]
    v = apply_guardrails({"verdict": "VERIFIED"}, {"critical": False}, assessments, sources)
    assert v["verdict"] == "VERIFIED"


def test_deadline_in_hours():
    assert "urgency" in codes("Your refund will be cancelled in 24 hours.")


def test_otp_requests_are_flagged():
    for msg in [
        "Enter your account number and OTP to receive the amount.",
        "Just share your UAN number and the OTP you receive with our agent.",
        "Turant OTP bhejo is number pe",
        "कृपया अपना ओटीपी बताएं",
    ]:
        assert "asks_otp_pin" in codes(msg), msg


def test_otp_warnings_are_not_flagged():
    for msg in [
        "RBI Kehta Hai: Never share your OTP, PIN, CVV or passwords with anyone.",
        "Kisi ke saath bhi apna OTP share mat karo.",
        "Do not share your UPI PIN with anyone.",
        "अपना ओटीपी कभी किसी को न बताएं।",
    ]:
        assert "asks_otp_pin" not in codes(msg), msg
