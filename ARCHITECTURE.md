# ProductGenie architecture

## End-to-end system flow

```mermaid
flowchart TD
  A[User opens ProductGenie] --> B[React/Vite loads App]
  B --> C[Create session via POST /session]
  C --> D[FastAPI validates environment and Neon session]
  D --> E[Chat screen ready]

  E --> F{User action}
  F -->|Text product request| G[POST /chat]
  F -->|Photo upload| H[POST /upload-photo]
  F -->|PDF upload| I[POST /upload-pdf]
  F -->|Open analytics| J[Load session products and history]

  G --> K[LangGraph classify intent]
  H --> L[Groq vision identifies safe category]
  I --> M[pdfplumber extracts PDF text]
  L --> N[Serper Shopping search]
  K -->|New search| N
  K -->|Compare or follow-up| O[Retrieve selected/session products]
  M --> P[Build conservative PDF product record]

  N --> Q[Normalize shopping listings]
  Q --> R[Google exact-title specification search]
  R --> S[Scrape linked retailer page]
  S --> T[Read visible text and JSON-LD fields]
  T --> U[Extract explicitly labeled specs]
  U --> V[Reject malformed values and preserve missing fields]
  V --> W[Store evidence in Neon]
  W --> X[Create MiniLM embeddings]
  X --> Y[Store vectors in Qdrant]

  O --> Z{Qdrant available and filter indexed?}
  Z -->|Yes| AA[Semantic retrieval and reranking]
  Z -->|No| AB[Fallback to Neon session products]
  AA --> AC[Keep selected products first]
  AB --> AC
  AC --> AD[Grounded response context]
  P --> AD
  Y --> AD

  AD --> AE[Groq generates concise grounded answer]
  AE --> AF[Persist user and assistant messages]
  AF --> AG[Return response and normalized products]
  AG --> AH[React renders chat cards and comparison controls]

  J --> AI[AnalyticsPage]
  AI --> AJ[Price, rating, retailer, radar, and feature breakdowns]
  AJ --> AK[Use exact source values; leave missing values blank]
```

## State

Every LangGraph turn carries `session_id`, `user_query`, `intent`, `chat_history`, `products`, and `response`. Upload paths additionally carry transient `image_bytes` or `pdf_text`. Product records are normalized as `name`, `brand`, `price`, `specs`, `imageUrl`, `source`, and `link`.

## Intent-routing graph

```text
START
  │
  ▼
classify_intent
  ├─ search ───► live_search (Serper /shopping; gl=in, hl=en)
  │                   │
  │                   └──► enrich all listings (Serper exact-title evidence + page text + JSON-LD)
  │                  ▼
  │             source-labeled specs ─► embed_and_store (MiniLM + Qdrant)
  │                                                 │
  ├─ photo ────► vision_identify (Groq vision) ─────┘
  │
  ├─ pdf ──────► parse_pdf (pdfplumber) ─► extract_specs
  │
  ├─ compare ──► retrieve_products (Qdrant; Neon fallback) ─► compare
  │
  └─ followup ─► load_chat_history (Neon Postgres) ─► rerank (Qdrant; Neon fallback)
                                                     │
                                                     ▼
                                                   respond (Groq)
                                                     │
                                                     ▼
                                           save_to_neon → END
```

## Data boundaries

- Serper receives every shopping search with `gl=in` and `hl=en` so prices/retailers are localized for India.
- Every normalized listing keeps the useful Serper result fields (price, rating, delivery, offers, ID, position, and any returned extensions), then receives exact-title search evidence, visible linked-page text, explicit JSON-LD product fields, and conservative label-aware specification extraction.
- Numeric labels are not freely inferred: `8GB RAM 512GB SSD` is kept as `8 GB` RAM and `512 GB` storage. Impossible values such as `000 mAh` are removed, and absent values remain absent.
- Sessions, messages, and product evidence are stored in Neon Postgres. Product embeddings are stored in Qdrant and filtered by session.
- A card selection is verified against trusted session records and placed first in the LLM context for both comparison and follow-up requests. If Qdrant rejects a session filter or is unavailable, persisted Neon product records keep the request usable.
- Responses are instructed to use only retrieved or uploaded evidence. They disclose absent details and discuss trade-offs, rather than inventing a universal winner.

## HTTP lifecycle

`POST /session` creates the session row. A chat or upload validates that session, invokes the graph asynchronously, persists user and assistant messages, and sends normalized products to the React interface. `GET /history/{session_id}` supports session-resume clients.


                         ┌──────────────────────┐
                         │        USER          │
                         │ ProductGenie Request │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   React / Vite UI    │
                         │   Chat Interface     │
                         └──────────┬───────────┘
                                    │
                         POST /session
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │       FastAPI        │
                         │ Session Validation   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     User Action?     │
                         └──────────┬───────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
             ▼                      ▼                      ▼
      ┌─────────────┐       ┌─────────────┐        ┌─────────────┐
      │ Text Query  │       │ Photo Upload│        │ PDF Upload  │
      └──────┬──────┘       └──────┬──────┘        └──────┬──────┘
             │                     │                      │
             ▼                     ▼                      ▼
      ┌─────────────┐       ┌─────────────┐        ┌─────────────┐
      │ LangGraph   │       │ Groq Vision │        │ pdfplumber  │
      │Intent Router│       │ Identify    │        │ Extract Text │
      └──────┬──────┘       │ Product     │        └──────┬──────┘
             │              └──────┬──────┘               │
             │                     │                      ▼
             │                     │               ┌─────────────┐
             │                     │               │Extract Specs│
             │                     │               └──────┬──────┘
             │                     │                      │
             ├──────────┐          │                      │
             │          │          │                      │
             ▼          ▼          ▼                      │
         ┌────────┐ ┌──────────┐ ┌──────────────┐         │
         │ Search │ │ Compare/ │ │ Serper       │         │
         │        │ │Follow-up │ │ Shopping     │         │
         └───┬────┘ └────┬─────┘ └──────┬───────┘         │
             │           │              │                 │
             │           │              ▼                 │
             │           │       ┌──────────────┐         │
             │           │       │ Normalize    │         │
             │           │       │ Products     │         │
             │           │       └──────┬───────┘         │
             │           │              │                 │
             │           │              ▼                 │
             │           │       ┌──────────────┐         │
             │           │       │ Exact Title  │         │
             │           │       │ Specification│         │
             │           │       │ Search       │         │
             │           │       └──────┬───────┘         │
             │           │              │                 │
             │           │              ▼                 │
             │           │       ┌──────────────┐         │
             │           │       │ Retailer Page│         │
             │           │       │ + JSON-LD    │         │
             │           │       └──────┬───────┘         │
             │           │              │                 │
             │           │              ▼                 │
             │           │       ┌──────────────┐         │
             │           │       │ Extract Valid│         │
             │           │       │ Explicit Specs│         │
             │           │       └──────┬───────┘         │
             │           │              │                 │
             │           │              ▼                 │
             │           │       ┌──────────────┐         │
             │           └──────►│ Neon Postgres│◄────────┘
             │                   │ Evidence DB  │
             │                   └──────┬───────┘
             │                          │
             │                          ▼
             │                   ┌──────────────┐
             │                   │ MiniLM       │
             │                   │ Embeddings   │
             │                   └──────┬───────┘
             │                          │
             │                          ▼
             │                   ┌──────────────┐
             │                   │ Qdrant       │
             │                   │ Vector DB    │
             │                   └──────┬───────┘
             │                          │
             └──────────────┬───────────┘
                            ▼
                  ┌──────────────────────┐
                  │ Product Retrieval    │
                  │ + Semantic Reranking │
                  └──────────┬───────────┘
                             │
                    Qdrant available?
                         /        \
                       Yes         No
                        │           │
                        ▼           ▼
                  ┌──────────┐ ┌──────────┐
                  │ Qdrant   │ │   Neon   │
                  │ Results  │ │ Fallback │
                  └────┬─────┘ └────┬─────┘
                       └──────┬──────┘
                              ▼
                    ┌──────────────────┐
                    │ Grounded Context │
                    │ Selected Products│
                    │ + Evidence       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Groq LLM       │
                    │ Generate Answer   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Save Conversation │
                    │   in Neon DB      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ React UI          │
                    │ Product Cards     │
                    │ Comparison        │
                    │ Recommendations   │
                    └──────────────────┘


Analytics Flow :

              User opens Analytics
                       │
                       ▼
              ┌─────────────────┐
              │ Analytics Page  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Load Products   │
              │ + Chat History  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Neon PostgreSQL │
              └────────┬────────┘
                       │
                       ▼
        ┌─────────────────────────────┐
        │ Analytics Processing        │
        │ • Price                     │
        │ • Rating                    │
        │ • Retailer                  │
        │ • Features                  │
        │ • Specification comparison  │
        └──────────────┬──────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Charts / Radar  │
              │ Feature Matrix  │
              └─────────────────┘