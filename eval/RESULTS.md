# ClaimCheck evaluation

Run 2026-10-15 15:02 on 50 messages (32 scams or false claims, 18 genuine) from [`dataset.jsonl`](dataset.jsonl). Models: Qwen/Qwen3.8-27B, nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/Nemotron-3-Ultra-550b-a55b, nvidia/Nemotron-3_5-Lightning, nvidia/nemotron-3-super-120b-a12b.

| Metric | Result |
|---|---|
| **Scams marked VERIFIED (called safe)** | **0 of 32** |
| Scams flagged as unsafe (SCAM or UNVERIFIED) | 100.0% |
| Scams labelled exactly SCAM | 100.0% |
| Genuine messages VERIFIED | 77.8% |
| Genuine messages wrongly called SCAM | 0 of 18 |
| Exact-label accuracy | 92.0% |
| **Zero-day scams caught** (invented, no search history) | **8/8** |
| Fingerprint alone (no search): scams flagged medium/high | 100.0% |
| Fingerprint alone: genuine messages flagged medium/high | 0/18 |
| Median / p90 time per check | 16.7s / 23.3s |
| Runs that errored | 0 |

**Confusion matrix** (rows: expected, columns: predicted)

| | SCAM | VERIFIED | UNVERIFIED |
|---|---|---|---|
| SCAM | 32 | 0 | 0 |
| VERIFIED | 0 | 14 | 4 |

**Correct by language:** english 30/34, hindi 5/5, hinglish 5/5, tamil 4/4, tanglish 2/2

## Misses

| id | lang | expected | got | fingerprint | headline |
|---|---|---|---|---|---|
| g01 | english | VERIFIED | UNVERIFIED | low 33 | PM-KISAN 21st instalment claim unverified |
| g02 | english | VERIFIED | UNVERIFIED | low 0 | RBI advisory on OTP sharing not confirmed by sources |
| g06 | english | VERIFIED | UNVERIFIED | low 50 | PM Surya Ghar scheme real but subsidy amount unverified |
| g13 | english | VERIFIED | UNVERIFIED | low 0 | Official e-EPIC download portal confirmed |
