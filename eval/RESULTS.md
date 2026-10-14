# ClaimCheck evaluation

Run 2026-10-14 22:03 on 40 messages (24 scams or false claims, 16 genuine) from [`dataset.jsonl`](dataset.jsonl). Models: Qwen/Qwen3.8-27B, nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/Nemotron-3-Ultra-550b-a55b, nvidia/Nemotron-3_5-Lightning, nvidia/nemotron-3-super-120b-a12b.

| Metric | Result |
|---|---|
| **Scams marked VERIFIED (called safe)** | **0 of 24** |
| Scams flagged as unsafe (SCAM or UNVERIFIED) | 100.0% |
| Scams labelled exactly SCAM | 100.0% |
| Genuine messages VERIFIED | 81.2% |
| Genuine messages wrongly called SCAM | 0 of 16 |
| Exact-label accuracy | 92.5% |
| Median / p90 time per check | 16.2s / 19.2s |
| Runs that errored | 0 |

**Confusion matrix** (rows: expected, columns: predicted)

| | SCAM | VERIFIED | UNVERIFIED |
|---|---|---|---|
| SCAM | 24 | 0 | 0 |
| VERIFIED | 0 | 13 | 3 |

**Correct by language:** english 26/29, hindi 4/4, hinglish 3/3, tamil 3/3, tanglish 1/1

## Misses

| id | lang | expected | got | headline |
|---|---|---|---|---|
| g02 | english | VERIFIED | UNVERIFIED | Genuine RBI safety advisory |
| g06 | english | VERIFIED | UNVERIFIED | PM Surya Ghar: 300 free units confirmed, subsidy amount unverified |
| g09 | english | VERIFIED | UNVERIFIED | DigiLocker legal validity unconfirmed |
