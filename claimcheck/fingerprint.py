"""Manipulation fingerprint: which persuasion tactics a message uses, independent of its facts.

Fact-checking needs search results; a scam invented today has none. The tactics, though, are
always the same. Nemotron scores nine tactics with quoted evidence in the original language,
and the deterministic red flags set a floor under the matching tactics, so a tactic found by
both is corroborated and one found only by rules still counts.
"""

TACTICS = {
    # key: (label, weight)
    "credential_request": ("Asks for OTP / PIN / bank details", 3.0),
    "payment_request": ("Asks you to pay or transfer money", 2.5),
    "off_channel": ("Moves you to an unofficial number, link or app", 2.0),
    "fear": ("Threatens loss, blocking or arrest", 2.0),
    "secrecy": ("Tells you to keep it secret", 2.0),
    "authority": ("Borrows government / bank authority", 1.5),
    "reward": ("Dangles free money or prizes", 1.5),
    "urgency": ("Artificial deadline", 1.5),
    "forward_pressure": ("Pushes you to forward it", 1.0),
}
# The tactics that actually take something from the victim.
ASKS = ("credential_request", "payment_request", "off_channel")
# Hooks that get the victim to comply.
HOOKS = ("authority", "reward", "fear")
# Pressure that stops the victim from thinking or checking.
PRESSURE = ("fear", "secrecy", "urgency", "forward_pressure")

# Deterministic red flag -> (tactic, minimum score)
RULE_FLOORS = {
    "asks_otp_pin": [("credential_request", 3)],
    "apk_download": [("off_channel", 3)],
    "fake_gov_domain": [("authority", 3), ("off_channel", 3)],
    "lookalike_domain": [("authority", 2), ("off_channel", 2)],
    "ip_link": [("off_channel", 3)],
    "shortener": [("off_channel", 2)],
    "risky_tld": [("off_channel", 2)],
    "punycode": [("off_channel", 2)],
    "upfront_fee": [("payment_request", 2)],
    "threat": [("fear", 2)],
    "prize": [("reward", 2)],
    "urgency": [("urgency", 1)],
    "forward_chain": [("forward_pressure", 2)],
}
MAX_RAW = 18.0  # weighted total that maps to 100


def build(model_out: dict | None, flags: list[dict]) -> dict:
    model_tactics = (model_out or {}).get("tactics") or {}
    tactics = {}
    for key, (label, weight) in TACTICS.items():
        m = model_tactics.get(key) or {}
        try:
            score = max(0, min(3, int(m.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        tactics[key] = {"label": label, "score": score, "evidence": str(m.get("evidence") or "")[:120],
                        "found_by": ["nemotron"] if score else []}

    for f in flags:
        for key, floor in RULE_FLOORS.get(f["code"], []):
            t = tactics[key]
            if t["score"] < floor:
                t["score"] = floor
                t["evidence"] = t["evidence"] or f["evidence"]
            t["found_by"] = sorted(set(t["found_by"]) | {"rules"})

    raw = sum(TACTICS[k][1] * t["score"] for k, t in tactics.items())
    asks = max(tactics[k]["score"] for k in ASKS)
    hooks = max(tactics[k]["score"] for k in HOOKS)
    pressure = max(tactics[k]["score"] for k in PRESSURE)
    if (asks >= 2 and hooks >= 2) or raw >= 12:
        level = "high"
    elif asks >= 2 or (pressure >= 2 and (hooks >= 2 or asks >= 1)):
        # Authority + reward alone is just what a genuine scheme announcement looks like.
        level = "medium"
    else:
        level = "low"

    active = sorted((k for k, t in tactics.items() if t["score"]), key=lambda k: -tactics[k]["score"] * TACTICS[k][1])
    t = {k: v["score"] for k, v in tactics.items()}
    # A link + an offer is also what ordinary marketing looks like. Only a playbook that takes
    # something from the victim (credentials, money, an .apk / fake-official link) or threatens
    # or isolates them is strong enough to call a scam without the model's judgement.
    forces_scam = level == "high" and (
        t["credential_request"] >= 2 or t["payment_request"] >= 2 or t["off_channel"] >= 3
        or t["fear"] >= 2 or t["secrecy"] >= 2
    )
    impersonates = (model_out or {}).get("impersonates")
    if not isinstance(impersonates, str) or impersonates.strip().lower() in {"", "null", "none", "n/a", "unknown"}:
        impersonates = None

    return {
        "level": level,
        "forces_scam": forces_scam,
        "score": min(100, round(raw / MAX_RAW * 100)),
        "tactics": tactics,
        "active": active,
        "impersonates": impersonates,
        "legit_signals": (model_out or {}).get("legit_signals") or [],
        "summary_en": (model_out or {}).get("summary_en") or "",
    }
