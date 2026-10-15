from claimcheck import fingerprint
from claimcheck.pipeline import apply_guardrails
from claimcheck.redflags import analyse


def model(**scores):
    return {"tactics": {k: {"score": v, "evidence": f"quote for {k}"} for k, v in scores.items()}}


def test_scam_playbook_is_high():
    fp = fingerprint.build(model(authority=3, reward=2, credential_request=3, urgency=2), [])
    assert fp["level"] == "high" and fp["score"] > 60
    assert fp["active"][0] == "credential_request"
    assert fp["tactics"]["authority"]["found_by"] == ["nemotron"]


def test_informational_message_is_low():
    fp = fingerprint.build(model(authority=1), [])
    assert fp["level"] == "low" and fp["active"] == ["authority"]


def test_rules_set_a_floor_and_corroborate():
    flags = analyse("Enter your OTP at pmkisan.gov.in.verify-now.xyz to get Rs 6000 today")["flags"]
    fp = fingerprint.build(model(credential_request=2), flags)
    cred = fp["tactics"]["credential_request"]
    assert cred["score"] == 3 and cred["found_by"] == ["nemotron", "rules"]
    assert fp["tactics"]["authority"]["score"] == 3 and fp["tactics"]["authority"]["found_by"] == ["rules"]
    assert fp["level"] == "high"


def test_model_failure_falls_back_to_rules():
    flags = analyse("Download SBI-Rewards.apk now")["flags"]
    fp = fingerprint.build(None, flags)
    assert fp["tactics"]["off_channel"]["score"] == 3


def test_bad_model_scores_are_clamped():
    fp = fingerprint.build({"tactics": {"urgency": {"score": "9"}, "fear": {"score": "x"}}}, [])
    assert fp["tactics"]["urgency"]["score"] == 3 and fp["tactics"]["fear"]["score"] == 0


def test_guardrail_high_manipulation_without_official_support_is_scam():
    fp = fingerprint.build(model(authority=3, reward=3, payment_request=3), [])
    v = apply_guardrails({"verdict": "UNVERIFIED"}, {"critical": False}, [], [], fp)
    assert v["verdict"] == "SCAM" and "manipulation" in v["guardrail_notes"][0]


def test_guardrail_keeps_officially_supported_verified():
    fp = fingerprint.build(model(authority=3, reward=3, payment_request=3), [])
    sources = [{"n": 1, "kind": "official"}]
    assessments = [{"stances": [{"n": 1, "stance": "supports"}]}]
    v = apply_guardrails({"verdict": "VERIFIED"}, {"critical": False}, assessments, sources, fp)
    assert v["verdict"] == "VERIFIED"
