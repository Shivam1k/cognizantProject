# ProductGenie

ProductGenie is an AI shopping assistant that finds, deep-researches, compares,
and recommends products — **any category**, not just electronics — through
natural conversation instead of manual browsing across multiple sites.

You describe what you need. It searches live shopping results, scrapes the
top listings (specs, description, customer reviews, and Q&A), scores them on
price/rating/review-sentiment/feature-match, and tells you which one is
genuinely the best pick and why — with the evidence to back it up. It then
remembers exactly which products you're comparing, so follow-up questions
("which has the best graphics?") stay scoped to those products until you
start a new search.

## What it does

- **Understands what you're looking for** — chat naturally, upload a product
  photo, or upload a PDF spec sheet.
- **Finds real products** — live Serper Shopping search, India-localized.
- **Reads deep into each product** — for the shortlist you're actually
  comparing (up to 12 products), it scrapes the product page *and* customer
  reviews *and* Q&A sections, not just the spec sheet.
- **Recommends, not just lists** — a deterministic rule-based scorer (price,
  rating, review sentiment, feature match) ranks the shortlist, and an LLM
  writes the plain-language justification for that ranking. The LLM never
  invents the ranking — only explains one that was already computed.
- **Works for any product category** — no hardcoded spec fields. An LLM
  classifies the category and extracts whatever attributes actually appear
  in the evidence (cushioning for shoes, wattage for blenders, RAM for
  laptops), each traced back to the exact sentence it came from.
- **Remembers the conversation, scoped correctly** — if you narrow down to a
  few products and ask follow-ups, the assistant stays focused on exactly
  those products (an "active product set") until you start a new search or
  ask for something else — never resets to "I just started" mid-comparison.
- **Visualizes the comparison** — price charts, feature breakdowns, and a
  "Why this pick" panel with a transparent, per-product score breakdown.
- **Shows product images on the right of the chat** — the panel highlights
  and scrolls to whichever products the latest reply is actually about.

### Analytics recommendation states

The Analytics page renders both **Overall Comparison** and **Final Verdict**
immediately. Until the on-demand AI recommendation finishes, those sections
show an appropriate empty or loading state; real recommendation scores and
verdict data replace that state when available. This is a frontend rendering
behavior only: the existing backend, API, and recommendation logic are
unchanged.

## Architecture

```text
React + Vite (5173)
  ├─ Chat, photo/PDF upload, product cards (highlight + scroll-to-active)
  └─ HTTP
       ▼
FastAPI (8000) ── Neon Postgres
       │              └─ sessions, messages, products, reviews, qna,
       │                 product_chunks, session_context (active set)
       ▼
LangGraph intent router
  ├─ search   → Serper Shopping → retailer/Serper enrichment
  │             → MiniLM product-level embed → Qdrant
  │             → resets the session's active product set
  │
  ├─ compare  → selected/retrieved shortlist (≤12)
  │             → ml/pipeline.deep_compare:
  │                 1. ml/scraping     — two-tier scrape (static + Playwright)
  │                                       reviews + Q&A, per-domain adapters
  │                 2. ml/feature_extraction — category classify + dynamic,
  │                                       source-traced attribute extraction
  │                 3. ml/services vector_store.index_chunks — chunk-level
  │                                       embeddings (spec / review / qna)
  │                 4. ml/recommendation — rule-based scorer (deterministic)
  │                                       + LLM justifier (explains, never
  │                                       re-ranks)
  │             → narrows the active product set to exactly these products
  │
  ├─ follow-up → filters to the session's active product set first
  │              (the "working memory" pointer), then grounds the answer in
  │              chunk-level RAG search restricted to that set
  │
  ├─ photo → Groq vision → Serper Shopping
  └─ PDF   → pdfplumber → product record → MiniLM + Qdrant
```

For the original step-by-step Mermaid flow of the base search/chat path, see
[ARCHITECTURE.md](ARCHITECTURE.md) (the deep-compare / recommendation /
active-set additions above are new on top of that base flow).

### How the "active product set" works (why follow-ups don't lose context)

Every session keeps a `session_context` row with the list of product keys the
conversation is currently scoped to:

- A **new search** replaces the active set with the new results.
- **Selecting products to compare** narrows the active set to exactly those.
- A **follow-up question** ("which has the best camera?") is answered only
  from the active set — not the whole session's history of every product
  you've ever looked at — until you search again or ask for something new.

This is what makes "I selected 5 laptops, now which has the best graphics?"
work correctly without the assistant losing track of which 5 you meant.

### Why the recommendation is two separate stages

1. **Rule-based scorer** (`ml/recommendation.py: score_products`) — pure
   arithmetic over price/rating/review-sentiment/feature-match. Deterministic:
   the same inputs always give the same ranking. This is what you can trust
   as a number.
2. **LLM justifier** (`ml/recommendation.py: justify_ranking`) — given that
   already-computed ranking and its evidence, writes the "why" in plain
   language. It is explicitly instructed not to change the order or invent a
   score — only to explain the one it was handed.

Keeping these separate means the ranking is auditable even if you don't trust
(or don't want to pay for) an LLM call for that part.

## Technology

- **Backend**: FastAPI, LangGraph, LangChain/Groq, Neon Postgres, Qdrant,
  Serper, BeautifulSoup, Playwright (deep review/Q&A scraping), pdfplumber.
- **Retrieval**: `sentence-transformers` (`all-MiniLM-L6-v2`) — one
  collection for product-level search, a second for chunk-level RAG
  (spec / review / Q&A chunks) used to ground follow-up answers.
- **Frontend**: React/Vite, Tailwind CSS, Axios, Recharts, lucide-react.

## Project map

```text
.
├─ backend/
│  ├─ main.py               FastAPI routes: /session /chat /recommend
│  │                         /upload-photo /upload-pdf /history
│  ├─ models.py              Product, Review, QnA, AttributeValue,
│  │                         ScoreBreakdown, RecommendationResponse, etc.
│  ├─ settings.py            Environment configuration
│  └─ requirements.txt       Python dependencies
├─ ml/
│  ├─ graph.py                LangGraph routing, active-set-aware follow-ups
│  ├─ services.py             Search, static scraping, embeddings (product +
│  │                          chunk level)
│  ├─ scraping.py             Deep scrape: reviews/Q&A, Playwright tier,
│  │                          per-domain adapters (Amazon/Flipkart/generic)
│  ├─ feature_extraction.py   Category classification + dynamic,
│  │                          category-agnostic attribute extraction
│  ├─ recommendation.py       Rule-based scorer + LLM justifier
│  └─ pipeline.py             Orchestrates scrape → extract → index → score
├─ database/
│  ├─ database.py            Neon persistence: sessions, messages, products,
│  │                         reviews, qna, product_chunks, session_context
│  └─ migrate_to_cloud.py    SQLite-to-Neon/Qdrant migration utility
├─ .env.example              Every required environment variable, documented
├─ start.ps1 / stop.ps1      One-command Windows launch/shutdown
├─ ARCHITECTURE.md           Base flow and data-boundary notes
└─ frontend/
   ├─ src/App.jsx             Session, theme, and route state
   ├─ src/api.js               Axios calls, incl. /recommend
   ├─ src/components/          Chat, product card (highlight/scroll-to),
   │                           upload, comparison, analytics UI
   ├─ src/components/analytics/WhyThisPick.jsx   Score-breakdown panel
   ├─ src/pages/                Landing, chat, analytics screens
   └─ public/                   Static branding assets
```

## API keys you need

Four accounts, all with usable free tiers. Sign up, then paste each key into
your `.env` file (copy `.env.example` to `.env` first).

| Key | What it's for | Get it at |
| --- | --- | --- |
| `GROQ_API_KEY` | LLM reasoning, vision, category classification, attribute extraction, recommendation justification | https://console.groq.com/keys |
| `SERPER_API_KEY` | Google Shopping search (finds real, current product listings) — free tier: 2,500 searches, no card | https://serper.dev |
| `DATABASE_URL` | Neon Postgres — chat history, products, reviews, Q&A, active product set | https://neon.tech (create a project, copy the connection string) |
| `QDRANT_URL` + `QDRANT_API_KEY` | Vector search — product-level and chunk-level RAG retrieval | https://cloud.qdrant.io (create a free cluster) |

See `.env.example` for the full list including model overrides and
deep-scrape tuning (`DEEP_SCRAPE_MAX_PRODUCTS`, `USE_PLAYWRIGHT`).

## Setup

```powershell
# 1. Copy and fill in your environment file
Copy-Item .env.example .env
# then edit .env with the 4 keys above

# 2. Backend
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
# Playwright needs its browser binary downloaded once (~300MB):
python -m playwright install chromium
# (Set USE_PLAYWRIGHT=false in .env to skip this — deep scraping still
#  works from static HTML, just misses some JS-rendered review widgets.)

# 3. Frontend
Set-Location frontend
npm.cmd install
```

## Run

### Recommended one-command shortcuts

```powershell
.\start.ps1
```

Stops stale listeners, starts the backend and Vite frontend, waits for both
health checks, and prints the URLs.

```powershell
.\stop.ps1
```

### Manual startup

Backend:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend (separate terminal):

```powershell
Set-Location frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. FastAPI docs (try the API directly) are at
`http://127.0.0.1:8000/docs`.

## API

| Method | Route | Description |
| --- | --- | --- |
| POST | `/session` | Creates a persistent session and returns `session_id`. |
| POST | `/chat` | `{session_id, message, selected_products}` → answer, products, `recommendation` (when a comparison ran), `active_product_keys`. |
| POST | `/recommend` | `{session_id, products, user_query, priorities}` → deep-scrapes the given shortlist and returns a scored, justified `RecommendationResponse`. Powers the "Why this pick" panel on demand. |
| POST | `/upload-photo?session_id=...` | Vision-identifies a category and searches similar products. |
| POST | `/upload-pdf?session_id=...` | Parses a PDF specification sheet and indexes its product data. |
| GET | `/history/{session_id}` | Returns saved user and assistant messages in order. |

## Grounding and limitations

Product facts originate only from Serper results, linked retailer pages,
scraped reviews/Q&A, or uploaded PDFs. Every dynamically extracted attribute
carries a `source_snippet` back to the exact evidence text it came from — the
extractor is instructed to skip anything not explicitly stated rather than
infer it.

Deep scraping (reviews + Q&A) only runs for the shortlist actually being
compared (max `DEEP_SCRAPE_MAX_PRODUCTS`, default 12), not the full search
result set, and is cached per session — a product already deep-scraped in
this session is not re-scraped. Some retailers block automated scraping
(403s/CAPTCHAs); when that happens the pipeline falls back gracefully to
whatever static-HTML or Serper-search evidence it can get rather than failing
the whole comparison.

Product/review/Q&A evidence is stored per session in Neon Postgres; both
product-level and chunk-level embeddings are stored in Qdrant. Follow-up
retrieval scopes to the session's active product set first, and falls back to
whole-session semantic search only when no active set has been established
yet. To migrate an existing local database, run
`python -m database.migrate_to_cloud` after configuring cloud credentials.
