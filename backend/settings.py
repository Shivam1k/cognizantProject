"""Application configuration loaded from the local environment."""

from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", os.getenv("POSTGRESS", ""))
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "productgenie_products")
# Chunk-level collection: one point per review/spec/Q&A chunk instead of one
# point per whole product, so retrieval can ground a specific follow-up
# ("best graphics?") in the exact chunk that answers it.
QDRANT_CHUNK_COLLECTION = os.getenv("QDRANT_CHUNK_COLLECTION", "productgenie_chunks")
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")
# This is configurable because Groq's available model catalogue can change.
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

# Deep-scrape / recommendation tuning
DEEP_SCRAPE_MAX_PRODUCTS = int(os.getenv("DEEP_SCRAPE_MAX_PRODUCTS", "12"))
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "true").strip().lower() != "false"
