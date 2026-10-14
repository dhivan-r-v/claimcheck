import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/").rstrip("/")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
_cache_dir = os.getenv("SEARCH_CACHE_DIR", "")
SEARCH_CACHE_DIR = Path(_cache_dir) if _cache_dir else None

# One model per job. Nemotron does all the reasoning; Qwen only transcribes screenshots
# because no Nemotron model on Token Factory accepts image input.
MODELS = {
    "vision": os.getenv("MODEL_VISION", "Qwen/Qwen3.8-27B"),
    # Lightning read Tamil/Hindi correctly where Nano misread them; Nano is fine for English queries.
    "understand": os.getenv("MODEL_UNDERSTAND", "nvidia/Nemotron-3_5-Lightning"),
    "plan": os.getenv("MODEL_PLAN", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    "assess": os.getenv("MODEL_ASSESS", "nvidia/nemotron-3-super-120b-a12b"),
    "verdict": os.getenv("MODEL_VERDICT", "nvidia/Nemotron-3-Ultra-550b-a55b"),
    "verdict_fallback": os.getenv("MODEL_VERDICT_FALLBACK", "nvidia/nemotron-3-super-120b-a12b"),
}

MAX_CLAIMS = 3
MAX_TEXT_CHARS = 4000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "15"))
CACHE_SIZE = 256

# Domains treated as official sources when searching and when judging links.
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov")
OFFICIAL_DOMAINS = {
    "rbi.org.in", "npci.org.in", "sebi.gov.in", "uidai.gov.in", "epfindia.gov.in",
    "incometax.gov.in", "irctc.co.in", "indiapost.gov.in", "sbi.co.in", "onlinesbi.sbi",
    "lic.in", "licindia.in", "bsnl.co.in", "who.int", "mygov.in",
}
FACT_CHECK_DOMAINS = [
    "pib.gov.in", "factly.in", "boomlive.in", "altnews.in", "newschecker.in",
    "vishvasnews.com", "thequint.com", "indiatoday.in", "factcrescendo.com",
]
