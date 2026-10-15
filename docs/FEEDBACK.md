# Feedback: Nebius Token Factory, AI Cloud, NVIDIA Nemotron and Tavily

Notes collected while building ClaimCheck (Oct 2026), for the hackathon's feedback section. Each item says what
happened, why it mattered, and a concrete suggestion.

## Nebius Token Factory

**What worked well**
- **One OpenAI-compatible API for every model.** Four Nemotron models and a vision model (Qwen3.8-27B) are served
  from one base URL with one key. Swapping the model for any pipeline stage is a one-line config change, which made
  it cheap to A/B models per stage. (That's how we found Lightning reads Tamil better than Nano.)
- **`/v1/models?verbose=true` returns each model's modality** (`text->text`, `text+image->text`). That told us
  immediately that no Nemotron model accepts images, before we wrote any code.
- **Latency is good enough for an interactive agent.** Seven model and search steps finish in about 16 s (median),
  with parallel calls.

**What could be better**
1. **The reasoning switch is hard to discover.** `chat_template_kwargs: {"enable_thinking": false}` cut Nemotron
   output from ~130–400 tokens to ~10 for the same answer and made calls 2–3x faster. We only found it by trial
   and error, and a `/no_think` system prompt did *not* work. *Suggestion:* a documented, model-agnostic
   `reasoning: off|low|high` parameter, plus a note on each Nemotron model card.
2. **Reasoning output lands in different places.** With thinking on, some models return the trace in
   `reasoning_content`, while Lightning sometimes put "Here's a thinking process…" into `content` when
   `max_tokens` was small. *Suggestion:* always separate the reasoning from `content`, and document what happens when
   `max_tokens` runs out mid-reasoning.
3. **No Nemotron vision model on Token Factory.** For a multimodal app we had to add a non-NVIDIA model just to read
   screenshots. *Suggestion:* serve an NVIDIA vision-language model (e.g. a Nemotron VL / Nano VL variant).
4. **No structured-output guarantee.** We wrote a JSON extractor that strips think tags and code fences and retries
   once. *Suggestion:* support `response_format: {"type": "json_schema"}` for Nemotron models, or say clearly in the
   docs if it is already supported.
5. **Per-request cost visibility.** It is hard to estimate how long a ~$30 balance lasts. *Suggestion:* return the
   cost of each request alongside `usage`, or show per-model spend in the console.

## Nebius AI Cloud (Serverless)

1. **No Nebius CLI for Windows.** The install docs cover Ubuntu and macOS only. Windows developers have to use
   Cloud Shell or WSL. *Suggestion:* a Windows build (or a winget/scoop package), or a clear pointer to Cloud Shell
   on the install page.
2. **Default disk size and platform are surprising for small services.** Endpoints default to a 250 GiB disk and a
   GPU platform. For a CPU web app this is easy to over-provision by accident, and disks are billed while stopped.
   *Suggestion:* when `--platform` is a CPU platform, default to a small disk, and show an estimated hourly cost
   before creation in the CLI and console.
3. **No scale-to-zero for endpoints.** Hackathon demos are idle most of the time, and judging happens weeks later.
   Without scale-to-zero, a small always-on endpoint competed with the inference budget, so we hosted the web tier
   elsewhere and kept Nebius for inference and batch evaluation (Serverless Job). *Suggestion:* scale-to-zero, or
   a free idle tier for hackathon participants.
4. **CPU price discoverability.** We couldn't find a per-vCPU-hour price for `cpu-d3` in the docs. *Suggestion:*
   list prices next to each platform/preset in the compute docs.

## NVIDIA Nemotron models

1. **Clear tiers make per-stage model choice easy.** Ultra for the final reasoned verdict, Super for evidence and
   manipulation analysis, Lightning and Nano for fast extraction. This is exactly the split the track description
   suggested, and it worked.
2. **Multilingual quality differs by size in ways that aren't documented.** On a Tamil electricity-scam message,
   Nano misread *மின் இணைப்பு* (electricity connection) as a broadband connection, while Lightning and Super read
   it correctly. *Suggestion:* publish per-language benchmarks for Indic languages and code-mixed text
   (Hinglish/Tanglish) for each Nemotron size.
3. **Temperature 0 matters for agents.** At the default temperature, the evidence stance for the same source flipped
   between runs, which flipped a VERIFIED verdict. Pinning temperature 0 fixed it. *Suggestion:* recommend low
   temperature for tool or judgement steps in the Nemotron agent docs.

## Tavily

1. **`include_domains` + `topic="news"` + Extract is a great combination for grounding.** Limiting one search to
   `gov.in`/`nic.in`, another to Indian fact-checkers and a third to recent news gave clean, separable evidence.
2. **The usage counter lagged.** The `/usage` endpoint still reported 46 credits after two full evaluation runs that
   actually used several hundred. *Suggestion:* real-time usage, or document the delay.
3. **Extract fails silently on JavaScript-heavy government portals.** Some results contain only "JavaScript must be
   enabled". *Suggestion:* a flag in Search and Extract results for "no usable content", or optional JS rendering
   for Extract.
4. **Built-in caching for evaluation.** We added a disk cache so evaluation reruns don't spend credits.
   *Suggestion:* a deterministic or cached mode for repeated identical queries during development.
