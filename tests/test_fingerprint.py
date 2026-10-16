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


def test_genuine_scheme_announcement_is_low():
    # "Ayushman Bharat gives Rs 5 lakh cover": authority + reward, but asks nothing and applies no pressure.
    fp = fingerprint.build(model(authority=3, reward=3), [])
    assert fp["level"] == "low"


def test_misinformation_with_pressure_is_medium():
    # "RBI: Rs 500 notes invalid next month, forward to everyone": no ask, but authority + pressure.
    fp = fingerprint.build(model(authority=3, urgency=2, forward_pressure=2), [])
    assert fp["level"] == "medium"


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


def test_marketing_link_and_offer_is_not_forced_to_scam():
    # "Personal loan up to Rs 10 lakh, check eligibility in 2 minutes: http://pw5.in/..." from a real lender
    fp = fingerprint.build(model(off_channel=2, reward=2, urgency=2), [])
    assert fp["level"] == "high" and not fp["forces_scam"]
    v = apply_guardrails({"verdict": "UNVERIFIED"}, {"critical": False}, [], [], fp)
    assert v["verdict"] == "UNVERIFIED"


def test_playbooks_that_take_something_still_force_scam():
    for asks in ({"credential_request": 3}, {"payment_request": 2}, {"off_channel": 3}, {"secrecy": 2, "off_channel": 2}):
        fp = fingerprint.build(model(authority=3, reward=2, **asks), [])
        assert fp["forces_scam"], asks


def test_null_impersonation_is_dropped():
    for value in ("null", "None", "", None, 0):
        assert fingerprint.build({"tactics": {}, "impersonates": value}, [])["impersonates"] is None
    assert fingerprint.build({"tactics": {}, "impersonates": "TRAI"}, [])["impersonates"] == "TRAI"


def test_internal_names_are_removed_but_citations_kept():
    v = apply_guardrails({"verdict": "SCAM", "explanation_en": "A classic off-channel trick [red flags]. See [1, 3].",
                          "reply_local": "Fake [red_flags, manipulation_fingerprint] link [2]."},
                         {"critical": False}, [], [])
    assert v["explanation_en"] == "A classic off-channel trick. See [1, 3]."
    assert v["reply_local"] == "Fake link [2]."
