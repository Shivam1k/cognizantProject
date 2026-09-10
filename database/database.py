"""Neon Postgres persistence helpers for ProductGenie sessions and evidence."""

import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from backend.settings import DATABASE_URL


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    """Yield a Neon Postgres connection with dictionary-like rows."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database() -> None:
    """Create the durable session, message, and product-evidence tables."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                product_name TEXT
            );
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT CHECK(role IN ('user', 'assistant')) NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                session_id TEXT NOT NULL,
                product_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, product_key),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)
        # Deep-scrape evidence, stored separately from the product payload so
        # the recommendation engine can reason about "300 reviews, 4.3 stars,
        # complaints about battery" distinctly from the raw spec sheet.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                product_key TEXT NOT NULL,
                rating REAL,
                text TEXT NOT NULL,
                author TEXT DEFAULT '',
                review_date TEXT DEFAULT '',
                verified_purchase BOOLEAN DEFAULT FALSE,
                source TEXT DEFAULT '',
                scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qna (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                product_key TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT DEFAULT '',
                source TEXT DEFAULT '',
                scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reviews_session_product
                ON reviews (session_id, product_key);
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_qna_session_product
                ON qna (session_id, product_key);
            """)
        # Mirrors what is embedded in the Qdrant chunk collection, kept here
        # purely for auditability (so every RAG chunk traces back to a row).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS product_chunks (
                chunk_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                product_key TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)
        # The "working memory" pointer: which products the conversation is
        # currently scoped to. Follow-ups filter through this set until the
        # user starts a new search or explicitly asks for something else.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_context (
                session_id TEXT PRIMARY KEY,
                active_product_keys TEXT NOT NULL DEFAULT '[]',
                last_intent TEXT DEFAULT '',
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            """)


def create_session(session_id: str) -> None:
    """Persist a new session id; repeated calls are harmless."""
    with connection() as conn:
        conn.execute("INSERT INTO sessions(session_id) VALUES (%s) ON CONFLICT DO NOTHING", (session_id,))


def session_exists(session_id: str) -> bool:
    """Return whether a session id has been created previously."""
    with connection() as conn:
        return conn.execute("SELECT 1 FROM sessions WHERE session_id = %s", (session_id,)).fetchone() is not None


def get_session_product_name(session_id: str) -> str:
    """Return the category this chat is dedicated to, if one has been searched."""
    with connection() as conn:
        row = conn.execute("SELECT product_name FROM sessions WHERE session_id = %s", (session_id,)).fetchone()
    return str(row["product_name"] or "") if row else ""


def set_session_product_name(session_id: str, product_name: str) -> None:
    """Store the latest product search context without limiting the conversation."""
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET product_name = %s WHERE session_id = %s",
            (product_name, session_id),
        )


def save_message(session_id: str, role: str, content: str) -> None:
    """Append one user or assistant message to a session's durable history."""
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, content),
        )


def get_history(session_id: str) -> list[dict[str, str]]:
    """Return all session messages in chronological order for context and API clients."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id = %s ORDER BY id", (session_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def save_products(session_id: str, products: list[dict]) -> None:
    """Upsert normalized, source-backed product records for later RAG retrieval."""
    rows = []
    for product in products:
        key = "|".join(str(product.get(field, "")) for field in ("name", "price", "source", "link"))
        rows.append((session_id, key, json.dumps(product, ensure_ascii=False)))
    if not rows:
        return
    with connection() as conn:
        conn.cursor().executemany(
            """
            INSERT INTO products(session_id, product_key, payload)
            VALUES (%s, %s, %s)
            ON CONFLICT(session_id, product_key) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def get_products(session_id: str) -> list[dict]:
    """Load the complete normalized evidence set for a persisted chat session."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT payload FROM products WHERE session_id = %s ORDER BY updated_at, product_key", (session_id,)
        ).fetchall()
    records: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
            if isinstance(payload, dict):
                records.append(payload)
        except (TypeError, json.JSONDecodeError):
            continue
    return records


def product_key_for(product: dict) -> str:
    """Build the same stable identity key used across products/reviews/qna/chunks."""
    return "|".join(str(product.get(field, "")) for field in ("name", "price", "source", "link"))


def save_reviews(session_id: str, product_key: str, reviews: list[dict]) -> None:
    """Persist scraped reviews for one product, keyed by the shared product_key."""
    if not reviews:
        return
    rows = [
        (
            session_id,
            product_key,
            review.get("rating"),
            str(review.get("text", ""))[:4000],
            str(review.get("author", ""))[:200],
            str(review.get("date", ""))[:100],
            bool(review.get("verified_purchase", False)),
            str(review.get("source", ""))[:200],
        )
        for review in reviews
        if str(review.get("text", "")).strip()
    ]
    if not rows:
        return
    with connection() as conn:
        conn.cursor().executemany(
            """
            INSERT INTO reviews(session_id, product_key, rating, text, author, review_date, verified_purchase, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


def get_reviews(session_id: str, product_key: str) -> list[dict]:
    """Return every scraped review stored for a product within a session."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT rating, text, author, review_date, verified_purchase, source "
            "FROM reviews WHERE session_id = %s AND product_key = %s ORDER BY id",
            (session_id, product_key),
        ).fetchall()
    return [
        {
            "rating": row["rating"],
            "text": row["text"],
            "author": row["author"],
            "date": row["review_date"],
            "verified_purchase": row["verified_purchase"],
            "source": row["source"],
        }
        for row in rows
    ]


def save_qna(session_id: str, product_key: str, entries: list[dict]) -> None:
    """Persist scraped Q&A pairs for one product, keyed by the shared product_key."""
    rows = [
        (session_id, product_key, str(entry.get("question", ""))[:1000], str(entry.get("answer", ""))[:2000], str(entry.get("source", ""))[:200])
        for entry in entries
        if str(entry.get("question", "")).strip()
    ]
    if not rows:
        return
    with connection() as conn:
        conn.cursor().executemany(
            "INSERT INTO qna(session_id, product_key, question, answer, source) VALUES (%s, %s, %s, %s, %s)",
            rows,
        )


def get_qna(session_id: str, product_key: str) -> list[dict]:
    """Return every scraped Q&A pair stored for a product within a session."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT question, answer, source FROM qna WHERE session_id = %s AND product_key = %s ORDER BY id",
            (session_id, product_key),
        ).fetchall()
    return [dict(row) for row in rows]


def has_deep_scrape(session_id: str, product_key: str) -> bool:
    """Return whether this product already has cached review/Q&A evidence.

    Acts as the scrape cache: once a shortlisted product has been deep
    scraped in this session, later comparisons reuse the stored evidence
    instead of re-scraping the same page.
    """
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM reviews WHERE session_id = %s AND product_key = %s LIMIT 1",
            (session_id, product_key),
        ).fetchone()
    return row is not None


def save_product_chunks(session_id: str, product_key: str, chunks: list[dict]) -> None:
    """Mirror chunk-level RAG text in Postgres for auditability alongside Qdrant."""
    rows = [
        (chunk["chunk_id"], session_id, product_key, chunk.get("chunk_type", "spec"), chunk.get("text", ""))
        for chunk in chunks
        if chunk.get("text", "").strip()
    ]
    if not rows:
        return
    with connection() as conn:
        conn.cursor().executemany(
            """
            INSERT INTO product_chunks(chunk_id, session_id, product_key, chunk_type, text)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET text = excluded.text
            """,
            rows,
        )


def set_active_products(session_id: str, product_keys: list[str], intent: str = "") -> None:
    """Replace the session's active product set (the chat's current working memory)."""
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO session_context(session_id, active_product_keys, last_intent, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (session_id) DO UPDATE SET
                active_product_keys = excluded.active_product_keys,
                last_intent = excluded.last_intent,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, json.dumps(product_keys), intent),
        )


def get_active_products(session_id: str) -> list[str]:
    """Return the product keys the conversation is currently scoped to, if any."""
    with connection() as conn:
        row = conn.execute(
            "SELECT active_product_keys FROM session_context WHERE session_id = %s", (session_id,)
        ).fetchone()
    if not row:
        return []
    try:
        keys = json.loads(row["active_product_keys"])
        return keys if isinstance(keys, list) else []
    except (TypeError, json.JSONDecodeError):
        return []
