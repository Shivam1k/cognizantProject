"""Copy existing local SQLite sessions and products into Neon and Qdrant."""

import json
import sqlite3
from pathlib import Path

from backend.models import Product
from database.database import create_session, save_message, save_products, set_session_product_name
from ml.services import vector_store


LOCAL_DATABASE = Path(__file__).resolve().parent.parent / "productgenie.db"


def migrate() -> None:
    """Migrate durable records; embeddings are regenerated for Qdrant."""
    if not LOCAL_DATABASE.exists():
        raise FileNotFoundError(f"Local database not found: {LOCAL_DATABASE}")
    with sqlite3.connect(LOCAL_DATABASE) as source:
        source.row_factory = sqlite3.Row
        sessions = source.execute("SELECT session_id, product_name FROM sessions").fetchall()
        for session in sessions:
            session_id = session["session_id"]
            create_session(session_id)
            if session["product_name"]:
                set_session_product_name(session_id, session["product_name"])
            for message in source.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ):
                save_message(session_id, message["role"], message["content"])
            products = []
            for row in source.execute("SELECT payload FROM products WHERE session_id = ?", (session_id,)):
                try:
                    products.append(Product.model_validate(json.loads(row["payload"])))
                except (TypeError, json.JSONDecodeError, ValueError):
                    continue
            if products:
                save_products(session_id, [product.model_dump() for product in products])
                vector_store.add(session_id, products, persist=False)
    print(f"Migrated {len(sessions)} session(s) to Neon and Qdrant.")


if __name__ == "__main__":
    migrate()
