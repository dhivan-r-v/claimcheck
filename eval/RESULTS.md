# ClaimCheck evaluation

Run 2026-10-16 20:47 on 50 messages (32 scams or false claims, 18 genuine) from [`dataset.jsonl`](dataset.jsonl). Models: Qwen/Qwen3.8-27B, nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/Nemotron-3-Ultra-550b-a55b, nvidia/Nemotron-3_5-Lightning, nvidia/nemotron-3-super-120b-a12b.

| Metric | Result |
|---|---|
| **Scams marked VERIFIED (called safe)** | **0 of 32** |
| Scams flagged as unsafe (SCAM or UNVERIFIED) | 100.0% |
| Scams labelled exactly SCAM | 96.9% |
| Genuine messages VERIFIED | 66.7% |
| Genuine messages wrongly called SCAM | 0 of 18 |
| Exact-label accuracy | 86.0% |
| **Zero-day scams caught** (invented, no search history) | **8/8** |
| Fingerprint alone (no search): scams flagged medium/high | 100.0% |
| Fingerprint alone: genuine messages flagged medium/high | 0/18 |
| Median / p90 time per check | 13.5s / 19.8s |
| Runs that errored | 0 |

**Confusion matrix** (rows: expected, columns: predicted)

| | SCAM | VERIFIED | UNVERIFIED |
|---|---|---|---|
| SCAM | 31 | 0 | 1 |
| VERIFIED | 0 | 12 | 6 |

**Correct by language:** english 28/34, hindi 5/5, hinglish 5/5, tamil 3/4, tanglish 2/2

## Misses

| id | lang | expected | got | fingerprint | headline |
|---|---|---|---|---|---|
| s15 | english | SCAM | UNVERIFIED | medium 58 | Government call recording and arrest claims are false |
| g01 | english | VERIFIED | UNVERIFIED | low 0 | PM-KISAN 21st instalment claim unverified |
| g02 | english | VERIFIED | UNVERIFIED | low 0 | RBI warns never share OTP PIN CVV passwords |
| g07 | english | VERIFIED | UNVERIFIED | low 33 | PM Vishwakarma loan details unverified |
| g10 | tamil | VERIFIED | UNVERIFIED | low 33 | Scheme offers ₹1,000 monthly, await official confirmation |
| g13 | english | VERIFIED | UNVERIFIED | low 0 | Election Commission confirms e-EPIC download portal |
| g17 | english | VERIFIED | UNVERIFIED | low 25 | UIDAI confirms myAadhaar portal for document updates |
