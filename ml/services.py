"""External-tool adapters plus local semantic product retrieval."""

import asyncio
import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import requests
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from backend.models import Product
from backend.settings import (
    GROQ_API_KEY,
    QDRANT_API_KEY,
    QDRANT_CHUNK_COLLECTION,
    QDRANT_COLLECTION,
    QDRANT_URL,
    SERPER_API_KEY,
    TEXT_MODEL,
)
from database.database import get_products as get_stored_products
from database.database import product_key_for, save_product_chunks, save_products


class Embedder(Protocol):
    """Small common interface shared by the optional ML and local embedders."""

    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> Any: ...


class HashingEmbedder:
    """Dependency-free, deterministic fallback for blocked ML runtimes.

    It is intentionally lightweight: token and token-pair hashes are projected
    into a fixed-size signed vector, then L2-normalized.  It preserves the
    vector-store contract without importing torch, sentence-transformers, or
    any other native ML runtime.
    """

    dimension = 384
    _tokens = re.compile(r"[a-z0-9]+")

    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            tokens = self._tokens.findall(str(text).lower())
            features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
            vector = [0.0] * self.dimension
            for feature in features:
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                number = int.from_bytes(digest, "big")
                index = number % self.dimension
                vector[index] += 1.0 if (number >> 8) & 1 else -1.0
            if normalize_embeddings:
                length = math.sqrt(sum(value * value for value in vector))
                if length:
                    vector = [value / length for value in vector]
            vectors.append(vector)
        return vectors


def _rows(embeddings: Any) -> list[list[float]]:
    """Normalize NumPy-like model output and fallback lists to plain vectors."""
    values = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
    return [[float(value) for value in row] for row in values]


class ProductVectorStore:
    """Qdrant-backed semantic product retrieval with session-level filtering."""

    def __init__(self) -> None:
        """Set up lazy embedding state so API startup remains quick."""
        self._model: Embedder | None = None
        self._products: dict[str, list[Product]] = {}
        self._client = (
            # Qdrant is optional retrieval infrastructure.  Avoid a blocking
            # compatibility call at API startup when the hosted instance is
            # unreachable; individual operations already fall back safely.
            QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=3, check_compatibility=False)
            if QDRANT_URL
            else None
        )
        self._collections: dict[str, str] = {}
        self.embedding_backend = "uninitialized"

    def _embedder(self) -> Embedder:
        """Load MiniLM lazily, or safely select the local hashing fallback."""
        if self._model is None:
            try:
                # Importing torch can fail under Windows Application Control,
                # so it must happen only inside this guarded code path.
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                self.embedding_backend = "sentence-transformers"
            except Exception:
                self._model = HashingEmbedder()
                self.embedding_backend = "hashing-fallback"
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return _rows(self._embedder().encode(texts, normalize_embeddings=True))

    @staticmethod
    def _collection_vector_size(collection: Any) -> int | None:
        vectors = getattr(getattr(getattr(collection, "config", None), "params", None), "vectors", None)
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict):
            for config in vectors.values():
                if hasattr(config, "size"):
                    return int(config.size)
        return None

    def _collection_for(self, base_name: str, vector_size: int) -> str | None:
        """Return a collection compatible with this embedder's vector size.

        Existing collections are never written with vectors of a different
        dimension.  A suffixed collection is used instead when an old model's
        collection is present, keeping both indexes readable and intact.
        """
        if self._client is None:
            return None
        cache_key = f"{base_name}:{vector_size}"
        if cache_key in self._collections:
            return self._collections[cache_key]
        try:
            names = {item.name for item in self._client.get_collections().collections}
            candidate = base_name
            if candidate in names:
                existing_size = self._collection_vector_size(self._client.get_collection(candidate))
                if existing_size != vector_size:
                    candidate = f"{base_name}_{vector_size}d"
            if candidate in names:
                existing_size = self._collection_vector_size(self._client.get_collection(candidate))
                if existing_size != vector_size:
                    # A manually created conflicting suffix is left untouched.
                    candidate = f"{base_name}_{vector_size}d_productgenie"
            if candidate not in names:
                self._client.create_collection(
                    collection_name=candidate,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
            self._collections[cache_key] = candidate
            return candidate
        except Exception:
            # Qdrant is additive retrieval infrastructure. The in-memory
            # session index remains useful if its service is unavailable.
            return None

    @staticmethod
    def _product_text(product: Product) -> str:
        """Convert product fields to searchable semantic text."""
        fields = [
            product.name,
            product.brand,
            product.price,
            product.description,
            product.offers,
        ]

        if product.rating is not None:
            fields.append(f"rating {product.rating}")

        if product.delivery:
            fields.append(product.delivery)

        fields.extend(
            f"{key} {value}" for key, value in product.specs.items()
        )

        return " ".join(
            str(value).strip()
            for value in fields
            if value is not None and str(value).strip()
        )

    def _load_session(self, session_id: str) -> None:
        """Rebuild a session index after an API restart from its stored evidence."""
        if session_id in self._products:
            return

        stored = []

        for record in get_stored_products(session_id):
            try:
                stored.append(Product.model_validate(record))
            except Exception:
                continue

        # Mark the session as loaded before calling add(), otherwise add()
        # would try to hydrate the same session recursively.
        self._products[session_id] = []

        if stored:
            self.add(session_id, stored, persist=False)

    def add(
        self,
        session_id: str,
        products: list[Product],
        *,
        persist: bool = True,
    ) -> None:
        """Embed and append products to the shared Qdrant collection."""
        self._load_session(session_id)

        seen = {
            (product.name, product.link)
            for product in self._products.get(session_id, [])
        }

        new_products: list[Product] = []

        for product in products:
            key = (product.name, product.link)

            if key in seen:
                continue

            seen.add(key)
            new_products.append(product)

        if not new_products:
            return

        embeddings = self._encode([self._product_text(product) for product in new_products])
        vector_size = len(embeddings[0])
        collection = self._collection_for(QDRANT_COLLECTION, vector_size)

        points = [
            PointStruct(
                id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"productgenie:{session_id}:{product.name}|"
                    f"{product.price}|{product.source}|{product.link}",
                ).hex,
                vector=vector,
                payload={
                    "session_id": session_id,
                    "product": product.model_dump(),
                },
            )
            for product, vector in zip(new_products, embeddings)
        ]

        if collection:
            try:
                self._client.upsert(collection_name=collection, points=points, wait=True)
            except Exception:
                # Keep the local/session product index usable if Qdrant is
                # temporarily unreachable; persisted records can be retried.
                pass

        self._products.setdefault(session_id, []).extend(new_products)

        if persist:
            save_products(
                session_id,
                [product.model_dump() for product in new_products],
            )

    def search(
        self,
        session_id: str,
        query: str,
        limit: int = 6,
    ) -> list[Product]:
        """Retrieve the session products semantically closest to a query."""
        self._load_session(session_id)

        products = self._products.get(session_id, [])

        if not products:
            return []

        vector = self._encode([query])[0]
        collection = self._collection_for(QDRANT_COLLECTION, len(vector))
        if not collection:
            return products[:limit]
        try:
            results = self._client.query_points(
                collection_name=collection,
                query=vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="session_id", match=MatchValue(value=session_id))
                    ]
                ),
                limit=limit,
                with_payload=True,
            ).points
        except Exception:
            return products[:limit]

        return [
            Product.model_validate(result.payload["product"])
            for result in results
            if result.payload and "product" in result.payload
        ]

    def selected(
        self,
        session_id: str,
        requested: list[Product],
    ) -> list[Product]:
        """Return client-selected listings only when they match trusted session records."""
        self._load_session(session_id)

        trusted = self._products.get(session_id, [])

        chosen: list[Product] = []
        seen: set[tuple[str, str, str, str]] = set()

        for product in requested:
            key = (
                product.name,
                product.price,
                product.source,
                product.link,
            )

            if key in seen:
                continue

            match = next(
                (
                    item
                    for item in trusted
                    if (
                        item.name,
                        item.price,
                        item.source,
                        item.link,
                    )
                    == key
                ),
                None,
            )

            if match:
                chosen.append(match)
                seen.add(key)

        return chosen

    def named(
        self,
        session_id: str,
        query: str,
    ) -> list[Product]:
        """Find a listing explicitly named in a follow-up without semantic guesswork."""
        self._load_session(session_id)

        normalized_query = re.sub(
            r"[^a-z0-9]+",
            " ",
            query.lower(),
        ).strip()

        if len(normalized_query) < 8:
            return []

        matches = []

        for product in self._products.get(session_id, []):
            normalized_name = re.sub(
                r"[^a-z0-9]+",
                " ",
                product.name.lower(),
            ).strip()

            # The full listing title may appear in a question, or a user may
            # type a distinctive title fragment such as "Mistborn Book 1".
            if len(normalized_name) >= 8 and (
                normalized_name in normalized_query
                or normalized_query in normalized_name
            ):
                matches.append(product)

        return matches

    # ------------------------------------------------------------------
    # Chunk-level RAG (reviews/specs/Q&A), used for deep-scraped products.
    #
    # A single product-level vector is too coarse once a product carries
    # dozens of reviews and Q&A pairs. Each product is split into typed
    # chunks (spec, review, qna) and embedded individually, so a follow-up
    # like "best graphics?" can retrieve the exact review/spec sentence
    # that answers it, filtered to only the products currently in focus.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_chunks(product: Product) -> list[dict[str, str]]:
        """Split one product's evidence into typed, independently-embeddable chunks."""
        key = product_key_for(product.model_dump())
        chunks: list[dict[str, str]] = []

        spec_text = " ".join([product.description] + [f"{k}: {v}" for k, v in product.specs.items()] + [f"{k}: {v.value}" for k, v in product.attributes.items()])
        if spec_text.strip():
            chunks.append({"chunk_id": f"{key}:spec", "chunk_type": "spec", "text": spec_text[:3000]})

        for index, review in enumerate(product.reviews[:30]):
            if review.text.strip():
                chunks.append({"chunk_id": f"{key}:review:{index}", "chunk_type": "review", "text": review.text[:1000]})

        for index, qa in enumerate(product.qna[:30]):
            text = f"Q: {qa.question} A: {qa.answer}".strip()
            if len(text) > 5:
                chunks.append({"chunk_id": f"{key}:qna:{index}", "chunk_type": "qna", "text": text[:1000]})

        return chunks

    def index_chunks(self, session_id: str, product: Product) -> None:
        """Embed and store every chunk for one deep-scraped product."""
        if self._client is None:
            return
        chunks = self._build_chunks(product)
        if not chunks:
            return
        product_key = product_key_for(product.model_dump())
        embeddings = self._encode([chunk["text"] for chunk in chunks])
        collection = self._collection_for(QDRANT_CHUNK_COLLECTION, len(embeddings[0]))
        if not collection:
            return
        points = [
            PointStruct(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"productgenie-chunk:{session_id}:{chunk['chunk_id']}").hex,
                vector=vector,
                payload={"session_id": session_id, "product_key": product_key, "chunk_type": chunk["chunk_type"], "text": chunk["text"]},
            )
            for chunk, vector in zip(chunks, embeddings)
        ]
        try:
            self._client.upsert(collection_name=collection, points=points, wait=True)
            save_product_chunks(session_id, product_key, chunks)
        except Exception:
            return

    def search_chunks(self, session_id: str, query: str, product_keys: list[str], limit: int = 8) -> list[str]:
        """Semantic search restricted to session + a specific set of active products."""
        if self._client is None or not product_keys or not query.strip():
            return []
        try:
            vector = self._encode([query])[0]
            collection = self._collection_for(QDRANT_CHUNK_COLLECTION, len(vector))
            if not collection:
                return []
            results = self._client.query_points(
                collection_name=collection,
                query=vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="session_id", match=MatchValue(value=session_id)),
                        FieldCondition(key="product_key", match=MatchAny(any=product_keys) if len(product_keys) > 1 else MatchValue(value=product_keys[0])),
                    ]
                ),
                limit=limit,
                with_payload=True,
            ).points
            return [result.payload.get("text", "") for result in results if result.payload]
        except Exception:
            return []


vector_store = ProductVectorStore()


def _string_value(value: Any) -> str:
    """Flatten a small structured-data value without fabricating any content."""
    if isinstance(value, dict):
        # Schema.org commonly represents brand and named values as an object;
        # its type label is metadata, not part of the user-facing value.
        for preferred_key in ("name", "value"):
            preferred = _string_value(value.get(preferred_key))

            if preferred:
                return preferred

        values = [_string_value(item) for item in value.values()]
        return ", ".join(item for item in values if item)

    if isinstance(value, list):
        values = [_string_value(item) for item in value]
        return ", ".join(item for item in values if item)

    return str(value).strip() if value is not None else ""


def _listing_specs(item: dict[str, Any]) -> dict[str, str]:
    """Keep useful non-price facts Serper includes, including undocumented extensions."""
    specs: dict[str, str] = {}

    labels = {
        "condition": "Condition",
        "availability": "Availability",
        "seller": "Seller",
        "merchant": "Merchant",
        "color": "Colour",
        "size": "Size",
    }

    for field, label in labels.items():
        value = _string_value(item.get(field))

        if value:
            specs[label] = value[:180]

    for container in (
        item.get("specs"),
        item.get("specifications"),
        item.get("extensions"),
    ):
        if isinstance(container, dict):
            pairs = container.items()
        elif isinstance(container, list):
            pairs = (
                (
                    f"Listing detail {index + 1}",
                    value,
                )
                for index, value in enumerate(container)
            )
        else:
            continue

        for key, value in pairs:
            clean_key = str(key).strip()
            clean_value = _string_value(value)

            if clean_key and clean_value:
                specs[clean_key[:80]] = clean_value[:180]

    return specs


def search_shopping(query: str) -> list[Product]:
    """Fetch India-localized Serper Shopping listings and normalize them as products."""
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is not configured.")

    try:
        response = requests.post(
            "https://google.serper.dev/shopping",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "gl": "in",
                "hl": "en",
            },
            timeout=20,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise RuntimeError(
            "Live product search is temporarily unavailable. "
            "Please try again shortly."
        ) from exc

    raw_items = response.json().get("shopping", [])

    products: list[Product] = []

    for item in raw_items[:8]:
        title = item.get("title", "Unnamed product")
        listed_price = str(
            item.get("price", "Price unavailable")
        )

        products.append(
            Product(
                name=title,
                brand=title.split()[0] if title else "Unknown",
                price=listed_price,
                specs=_listing_specs(item),
                imageUrl=item.get(
                    "imageUrl",
                    item.get("image", ""),
                ),
                # The visible retailer label must agree with the URL
                # the user can open.
                source=(
                    _retailer_name(str(item.get("link", "")))
                    if item.get("link")
                    else "Search result"
                ),
                link=item.get("link", ""),
                rating=item.get("rating", None),
                rating_count=item.get("ratingCount", None),
                delivery=item.get("delivery", ""),
                offers=item.get("offers", ""),
                product_id=str(item.get("productId", "")),
                position=item.get("position"),
                observed_price=listed_price,
            )
        )

    return products


def _json_ld_products(value: Any) -> list[dict[str, Any]]:
    """Return Product objects nested anywhere in a JSON-LD payload."""
    if isinstance(value, list):
        return [
            product
            for item in value
            for product in _json_ld_products(item)
        ]

    if not isinstance(value, dict):
        return []

    types = value.get("@type", [])

    if isinstance(types, str):
        types = [types]

    found = [
        value
    ] if any(
        str(item).lower() == "product"
        for item in types
    ) else []

    for nested in value.values():
        found.extend(_json_ld_products(nested))

    return found


def _retailer_name(url: str) -> str:
    """Return the retailer name from the final destination URL, never a search label."""
    host = (
        urlparse(url)
        .netloc
        .lower()
        .removeprefix("www.")
    )

    known_retailers = {
        "amazon.in": "Amazon",
        "flipkart.com": "Flipkart",
        "croma.com": "Croma",
        "reliancedigital.in": "Reliance Digital",
        "vijaysales.com": "Vijay Sales",
        "tatacliq.com": "Tata CLiQ",
        "myntra.com": "Myntra",
        "nykaa.com": "Nykaa",
    }

    for domain, name in known_retailers.items():
        if host == domain or host.endswith(f".{domain}"):
            return name

    return host or "Unknown retailer"


def _format_price(
    value: Any,
    currency: Any = "",
) -> str:
    """Format an explicit retailer price without interpreting or converting it."""
    raw = _string_value(value).replace(",", "").strip()

    match = re.search(
        r"\d+(?:\.\d{1,2})?",
        raw,
    )

    if not match:
        return ""

    amount = match.group(0)

    if "." not in amount:
        display_amount = f"{int(amount):,}"
    else:
        display_amount = (
            f"{float(amount):,.2f}"
            .rstrip("0")
            .rstrip(".")
        )

    currency_code = _string_value(currency).upper()

    if currency_code == "INR" or "₹" in raw:
        return f"₹{display_amount}"

    return f"{currency_code} {display_amount}".strip()


def _retailer_product_data(
    soup: BeautifulSoup,
) -> dict[str, Any]:
    """Read exact Product and Offer values published by the retailer page."""
    specs: dict[str, str] = {}

    brand = ""
    name = ""
    price = ""
    availability = ""

    fields = {
        "model": "Model",
        "sku": "SKU",
        "mpn": "MPN",
        "color": "Colour",
        "size": "Size",
        "material": "Material",
        "weight": "Weight",
        "dimensions": "Dimensions",
        "category": "Category",
    }

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    ):
        try:
            payload = json.loads(
                script.string or script.get_text()
            )
        except (TypeError, json.JSONDecodeError):
            continue

        for product in _json_ld_products(payload):
            if not name:
                name = _string_value(
                    product.get("name")
                )

            if not brand:
                brand = _string_value(
                    product.get("brand")
                )

            for field, label in fields.items():
                value = _string_value(
                    product.get(field)
                )

                if value:
                    specs[label] = value[:180]

            properties = product.get(
                "additionalProperty",
                [],
            )

            if isinstance(properties, dict):
                properties = [properties]

            for prop in properties:
                if not isinstance(prop, dict):
                    continue

                key = _string_value(
                    prop.get("name")
                    or prop.get("propertyID")
                )

                value = _string_value(
                    prop.get("value")
                )

                if key and value:
                    specs[key[:80]] = value[:180]

            offers = product.get("offers", [])

            if isinstance(offers, dict):
                offers = [offers]

            for offer in offers:
                if not isinstance(offer, dict):
                    continue

                if not price:
                    price = _format_price(
                        offer.get("price")
                        or offer.get("lowPrice"),
                        offer.get("priceCurrency"),
                    )

                if not availability:
                    availability = _string_value(
                        offer.get("availability")
                    ).rsplit("/", 1)[-1]

    if not price:
        meta_price = (
            soup.find(
                "meta",
                attrs={"property": "product:price:amount"},
            )
            or soup.find(
                "meta",
                attrs={"itemprop": "price"},
            )
        )

        meta_currency = (
            soup.find(
                "meta",
                attrs={"property": "product:price:currency"},
            )
            or soup.find(
                "meta",
                attrs={"itemprop": "priceCurrency"},
            )
        )

        price = _format_price(
            meta_price.get("content")
            if meta_price
            else "",
            meta_currency.get("content")
            if meta_currency
            else "",
        )

    return {
        "specs": specs,
        "brand": brand,
        "name": name,
        "price": price,
        "availability": availability,
    }


def _titles_match(
    listing_title: str,
    retailer_title: str,
) -> bool:
    """Reject a page when its product title is too different from the search listing."""

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(
                r"[a-z0-9]+",
                value.lower(),
            )
            if len(token) > 1
            and token
            not in {
                "with",
                "and",
                "for",
                "the",
                "new",
                "online",
                "buy",
                "price",
            }
        }

    listing_tokens = tokens(listing_title)
    retailer_tokens = tokens(retailer_title)

    if (
        len(listing_tokens) < 2
        or len(retailer_tokens) < 2
    ):
        return False

    overlap = (
        len(listing_tokens & retailer_tokens)
        / min(
            len(listing_tokens),
            len(retailer_tokens),
        )
    )

    return overlap >= 0.55


def _price_amount(price: str) -> float | None:
    """Return an INR-like numeric price only when the listing gives one explicitly."""
    match = re.search(
        r"\d[\d,]*(?:\.\d+)?",
        str(price),
    )

    if not match:
        return None

    try:
        amount = float(
            match.group(0).replace(",", "")
        )
    except ValueError:
        return None

    return amount if amount > 0 else None


def rank_live_offers(
    products: list[Product],
) -> list[Product]:
    """Put verified retailer offers first and make the lowest verified price deterministic."""
    for product in products:
        product.recommended = False

    ranked = sorted(
        products,
        key=lambda product: (
            not product.verified,
            _price_amount(product.price) is None,
            _price_amount(product.price)
            or float("inf"),
            product.name.lower(),
        ),
    )

    if (
        ranked
        and ranked[0].verified
        and _price_amount(ranked[0].price) is not None
    ):
        ranked[0].recommended = True

    return ranked


def lowest_verified_offer(
    products: list[Product],
) -> Product | None:
    """Return the lowest current retailer offer kept in the session RAG record."""
    for product in rank_live_offers(list(products)):
        if (
            product.verified
            and _price_amount(product.price) is not None
        ):
            return product

    return None


async def scrape_page_details(
    url: str,
) -> dict[str, Any]:
    """Fetch a retailer listing and return only page-published product evidence."""
    if not url:
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; ProductGenie/1.0)"
                )
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        html = response.text

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        description = soup.find(
            "meta",
            attrs={"name": "description"},
        )

        og_image = soup.find(
            "meta",
            property="og:image",
        )

        product_data = _retailer_product_data(soup)

        for element in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
            ]
        ):
            element.decompose()

        visible_text = " ".join(
            soup.stripped_strings
        )

        return {
            "description": (
                description.get("content", "")
                if description
                else ""
            ),
            "text": visible_text[:16000],
            "imageUrl": (
                og_image.get("content", "")
                if og_image
                else ""
            ),
            "url": str(response.url),
            "source": _retailer_name(
                str(response.url)
            ),
            **product_data,
        }

    except httpx.HTTPError:
        return {}


async def search_product_details(
    name: str,
) -> str:
    """Collect specification evidence from Serper Search snippets for one exact listing title."""
    if not name or not SERPER_API_KEY:
        return ""

    try:
        async with httpx.AsyncClient(
            timeout=20,
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
        ) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                json={
                    "q": (
                        f'"{name}" full specifications '
                        "RAM storage processor display "
                        "battery weight"
                    ),
                    "gl": "in",
                    "hl": "en",
                    "num": 10,
                },
            )

            response.raise_for_status()

        results = response.json().get(
            "organic",
            [],
        )

        evidence = []

        for result in results[:5]:
            title = str(
                result.get("title", "")
            ).strip()

            snippet = str(
                result.get("snippet", "")
            ).strip()

            if snippet:
                evidence.append(
                    (
                        f"Result title: {title}\n"
                        f"Details: {snippet}"
                        if title
                        else snippet
                    )
                )

        return "\n".join(evidence)

    except httpx.HTTPError:
        return ""


def extract_specs_from_source_text(
    text: str,
) -> dict[str, str]:
    """Extract only explicit, unit-labeled facts from Google result evidence."""
    if not text or not text.strip():
        return {}

    specs: dict[str, str] = {}

    numeric_patterns = {
        "RAM": [
            r"\b(\d+(?:\.\d+)?)\s*(gb|gib)\s*(?:ram|memory)\b",
            r"(?:ram|memory|system memory|installed memory)"
            r"\s*[:\-+]?\s*(\d+(?:\.\d+)?)\s*"
            r"(gb|gib|mb)\b",
        ],
        "Storage": [
            r"\b(\d+(?:\.\d+)?)\s*(tb|gb)"
            r"\s*(?:ssd|hdd|storage|rom)\b",
            r"(?:storage|internal storage|rom|ssd|hdd|hard disk|hard drive)"
            r"\s*[:\-+]?\s*(\d+(?:\.\d+)?)\s*"
            r"(tb|gb|mb)\b",
        ],
        "Battery": [
            r"(?:battery|battery capacity)"
            r"\s*[:\-+]?\s*(\d+(?:\.\d+)?)\s*(mah|wh)\b",
            r"\b(\d+(?:\.\d+)?)\s*(mah)\b",
        ],
        "Display": [
            r"(?:display|screen|panel|monitor)"
            r"\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(inches?|in|cm)\b",
            r"\b(\d+(?:\.\d+)?)\s*(inches?|in)"
            r"\s*(?:display|screen)\b",
        ],
        "Camera": [
            r"(?:camera|webcam|rear camera|front camera)"
            r"\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(mp|megapixels?)\b",
            r"\b(\d+(?:\.\d+)?)\s*(mp|megapixels?)"
            r"\s*(?:camera|webcam)\b",
        ],
        "Weight": [
            r"(?:weight|item weight|product weight)"
            r"\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams)\b",
            r"\b(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams)"
            r"\s*(?:weight)\b",
        ],
    }

    unit_aliases = {
        "gib": "GB",
        "gb": "GB",
        "mb": "MB",
        "tb": "TB",
        "in": "in",
        "inch": "in",
        "inches": "in",
        "kilogram": "kg",
        "kilograms": "kg",
        "grams": "g",
    }

    for label, patterns_for_label in numeric_patterns.items():
        for pattern in patterns_for_label:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                value, unit = match.groups()

                specs[label] = (
                    f"{value} "
                    f"{unit_aliases.get(unit.lower(), unit)}"
                )

                break

    resolution = re.search(
        r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b",
        text,
        re.IGNORECASE,
    )

    if resolution:
        specs["Resolution"] = (
            resolution.group(1)
            .replace(" ", "")
        )

    text_patterns = {
        "Processor": (
            r"\b((?:intel\s+(?:core\s+)?"
            r"(?:i[3579]|pentium|celeron)"
            r"(?:\s+[a-z0-9-]+)?|"
            r"amd\s+(?:ryzen|athlon)"
            r"(?:\s+[a-z0-9-]+)?|"
            r"(?:qualcomm\s+)?snapdragon"
            r"(?:\s+[0-9]+)?|"
            r"google\s+tensor"
            r"(?:\s+[a-z0-9]+)?|"
            r"mediatek\s+dimensity"
            r"(?:\s+[0-9]+)?|"
            r"apple\s+m[0-9]+))\b"
        ),
        "OS": (
            r"\b((?:windows\s+10|windows\s+11"
            r"(?:\s+pro|\s+home)?|macos|android|"
            r"ubuntu|linux|chrome\s+os))\b"
        ),
    }

    for label, pattern in text_patterns.items():
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            specs[label] = re.sub(
                r"\s+",
                " ",
                match.group(1),
            ).strip()

    return specs


def clean_product_specs(
    specs: dict[str, str],
) -> dict[str, str]:
    """Remove malformed source values without filling gaps with guesses."""
    cleaned: dict[str, str] = {}

    for key, value in specs.items():
        text = str(value).strip()

        if not text:
            continue

        normalized_key = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(key).lower(),
        ).strip()

        if (
            "battery" in normalized_key
            or normalized_key == "capacity"
        ):
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*(mah|wh)\b",
                text,
                re.IGNORECASE,
            )

            if (
                match
                and match.group(2).lower() == "mah"
                and float(match.group(1)) < 1000
            ):
                continue

            if (
                match
                and float(match.group(1)) <= 0
            ):
                continue

        cleaned[str(key)] = text

    return cleaned


def extract_specs_from_text(
    text: str,
) -> dict[str, str]:
    """Extract explicitly stated, category-appropriate specifications from page text."""
    if not text.strip() or not GROQ_API_KEY:
        return {}

    try:
        response = ChatGroq(
            api_key=GROQ_API_KEY,
            model=TEXT_MODEL,
            temperature=0.2,
            timeout=45,
            max_retries=1,
        ).invoke(
            [
                SystemMessage(
                    content=(
                        "Extract only specifications explicitly stated "
                        "for the exact product title in the supplied "
                        "evidence. Search snippets can describe closely "
                        "related variants, so omit any field with "
                        "conflicting values or no clear connection to "
                        "that exact title. Return ONLY a JSON object "
                        "whose keys and values are the supported "
                        "specifications found. Infer the relevant keys "
                        "from the text; do not use a fixed schema, "
                        "infer missing facts, or include commentary."
                    )
                ),
                HumanMessage(content=text),
            ]
        )

        content = str(
            response.content
        ).strip()

        if content.startswith("```"):
            content = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                content,
            ).strip()

        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            return {}

        return {
            str(key): str(value)
            for key, value in parsed.items()
            if (
                isinstance(key, str)
                and value is not None
                and str(value).strip()
            )
        }

    except Exception:
        return {}


async def enrich_products(
    products: list[Product],
) -> list[Product]:
    """
    Verify retailer pages while preserving a valid Serper Shopping
    price as a fallback.

    Price priority:

    1. Matching retailer page with explicit price
    2. Valid Serper Shopping observed_price
    3. Price unavailable
    """

    page_details, search_evidence = await asyncio.gather(
        asyncio.gather(
            *(
                scrape_page_details(product.link)
                for product in products
            )
        ),
        # Shopping results often only contain connectivity information. Fetch
        # source snippets for the exact listing title as a fallback for the
        # product specifications needed in the comparison breakdown.
        asyncio.gather(
            *(
                search_product_details(product.name)
                for product in products
            )
        ),
    )

    for product, page_detail, product_evidence in zip(
        products,
        page_details,
        search_evidence,
    ):
        # Many retailer pages expose specifications in visible page text but
        # omit them from JSON-LD. Extract only explicit values from that page
        # evidence so analytics is not limited to a lone listing extension
        # such as Network.
        page_evidence = "\n".join(
            str(page_detail.get(key, "")).strip()
            for key in ("description", "text")
            if page_detail.get(key)
        )

        verified_name = str(
            page_detail.get("name", "")
        ).strip()

        verified_price = str(
            page_detail.get("price", "")
        ).strip()

        verified_url = str(
            page_detail.get("url", "")
        ).strip()

        title_matches = _titles_match(
            product.name,
            verified_name,
        )
        page_specs = (
            extract_specs_from_source_text(page_evidence)
            if title_matches
            else {}
        )
        # The query is quoted with the listing title, so these snippets are a
        # fallback for product facts absent from the retailer page itself.
        snippet_specs = extract_specs_from_source_text(product_evidence)
        evidence_specs = {**snippet_specs, **page_specs}

        # IMPORTANT:
        # Preserve the original Serper Shopping price.
        #
        # This price is our fallback when the retailer page cannot
        # expose a static price, which commonly happens on dynamic
        # ecommerce pages.
        observed_price = _format_price(
            product.observed_price
        )

        if verified_url:
            product.link = verified_url
            product.source = str(
                page_detail.get(
                    "source",
                    product.source or "Unknown retailer",
                )
            )

        # ---------------------------------------------------------
        # CASE 1
        #
        # The retailer page matches the searched product and
        # provides an explicit price.
        #
        # This is our strongest price evidence.
        # ---------------------------------------------------------
        if title_matches and verified_price:
            product.name = verified_name
            product.price = verified_price

            # Structured retailer fields take precedence over text-derived
            # values, while the latter fill gaps such as RAM or processor.
            product.specs = clean_product_specs({
                **evidence_specs,
                **page_detail.get("specs", {}),
            })

            availability = str(
                page_detail.get(
                    "availability",
                    "",
                )
            ).strip()

            if availability:
                product.specs["Availability"] = availability

            product.verified = True

            product.verification_note = (
                f"Verified from {product.source} on "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}."
            )

            page_description = page_detail.get(
                "description",
                "",
            ).strip()

            page_text = page_detail.get(
                "text",
                "",
            ).strip()

            image_url = page_detail.get(
                "imageUrl",
                "",
            ).strip()

            evidence = "\n\n".join(
                part
                for part in (
                    f"Exact product title: {product.name}",
                    page_description,
                    page_text,
                )
                if part
            )

            if evidence:
                product.description = evidence

            if (
                product.brand == "Unknown"
                and page_detail.get("brand")
            ):
                product.brand = str(
                    page_detail["brand"]
                )

            if not product.imageUrl and image_url:
                product.imageUrl = image_url

            continue

        # ---------------------------------------------------------
        # CASE 2
        #
        # Retailer verification failed, OR the retailer page did
        # not provide a usable price.
        #
        # IMPORTANT:
        # Keep the valid Serper Shopping price instead of replacing
        # it with "Price unavailable".
        # ---------------------------------------------------------
        if observed_price:
            product.price = observed_price

            # We have a live Google Shopping price, but the retailer
            # page did not independently expose a matching static
            # price. Therefore, mark the source appropriately.
            product.verified = True

            product.verification_note = (
                f"Live {product.source} listing price retrieved "
                "from Google Shopping. Retailer page could not "
                "independently verify the current price; open the "
                "source link to recheck the checkout price."
            )

            # Keep specifications supplied by the live Shopping listing.
            # They were collected before retailer-page enrichment and are
            # still evidence for this exact listing. Clearing them here made
            # the analytics breakdown lose RAM, storage, processor, and
            # other available product details whenever page verification
            # could not obtain a static retailer price.
            product.specs = clean_product_specs({
                **product.specs,
                **evidence_specs,
            })

            continue

        # ---------------------------------------------------------
        # CASE 3
        #
        # Neither retailer verification nor Serper Shopping has
        # a usable price.
        #
        # Only now do we show "Price unavailable".
        # ---------------------------------------------------------
        product.price = "Price unavailable"
        product.verified = False
        product.specs = {}

        product.verification_note = (
            "Current price could not be verified from the "
            "available retailer or shopping sources."
        )

    return rank_live_offers(products)


def product_from_pdf_text(
    raw_text: str,
) -> Product:
    """Build a conservative local product record from extracted PDF text without inventing values."""
    lines = [
        line.strip()
        for line in raw_text.splitlines()
        if line.strip()
    ]

    name = (
        lines[0][:120]
        if lines
        else "Uploaded specification sheet"
    )

    specs: dict[str, str] = {}

    for line in lines[:80]:
        match = re.match(
            r"^([A-Za-z][A-Za-z0-9 /_-]{1,40})"
            r"\s*[:\-]\s*(.{1,120})$",
            line,
        )

        if match:
            specs[
                match.group(1).strip()
            ] = match.group(2).strip()

    return Product(
        name=name,
        specs=specs,
        source="Uploaded PDF",
    )


def compact_products(
    products: list[Product],
) -> str:
    """Serialize trusted product facts for a grounded LLM prompt."""
    return json.dumps(
        [
            product.model_dump()
            for product in products
        ],
        ensure_ascii=False,
    )
