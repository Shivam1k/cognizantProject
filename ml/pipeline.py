"""Deep-compare pipeline: scrape -> extract -> index -> score -> justify.

This is deliberately only run against a shortlist (the top 10-12 search
results, or fewer once the user narrows to specific products) rather than on
every search result — deep scraping is comparatively slow and fragile, so it
only runs for products someone actually wants compared.
"""

from __future__ import annotations

import asyncio

from backend.models import Product, QnA, RecommendationResponse, Review
from backend.settings import DEEP_SCRAPE_MAX_PRODUCTS
from database.database import (
    get_qna,
    get_reviews,
    has_deep_scrape,
    product_key_for,
    save_qna,
    save_reviews,
)
from ml.feature_extraction import enrich_with_dynamic_attributes
from ml.recommendation import recommend
from ml.scraping import deep_scrape_product
from ml.services import vector_store


async def _deep_scrape_one(session_id: str, product: Product) -> Product:
    key = product_key_for(product.model_dump())

    if has_deep_scrape(session_id, key):
        # Cache hit: reuse previously scraped evidence instead of re-scraping.
        cached_reviews = get_reviews(session_id, key)
        cached_qna = get_qna(session_id, key)
    else:
        scraped = await deep_scrape_product(product.link)
        cached_reviews = scraped.get("reviews", [])
        cached_qna = scraped.get("qna", [])
        save_reviews(session_id, key, cached_reviews)
        save_qna(session_id, key, cached_qna)

    product.reviews = [Review(**{**r, "date": r.get("date", "")}) for r in cached_reviews if r.get("text")]
    product.qna = [QnA(**q) for q in cached_qna if q.get("question")]
    product.deep_scraped = True
    return product


async def deep_compare(
    session_id: str,
    products: list[Product],
    user_query: str = "",
    priorities: dict[str, float] | None = None,
) -> tuple[list[Product], RecommendationResponse]:
    """Deep-scrape, category-classify, extract attributes, index chunks, and rank a shortlist."""
    shortlist = products[:DEEP_SCRAPE_MAX_PRODUCTS]
    if not shortlist:
        return [], RecommendationResponse(summary="No products to compare yet.")

    shortlist = await asyncio.gather(*(_deep_scrape_one(session_id, product) for product in shortlist))
    shortlist = list(shortlist)

    shortlist = await enrich_with_dynamic_attributes(shortlist)

    for product in shortlist:
        try:
            vector_store.index_chunks(session_id, product)
        except Exception:
            # Chunk indexing is additive grounding for follow-ups; a failure
            # here must never break the comparison itself.
            continue

    recommendation = await recommend(shortlist, user_query, priorities)

    winner_key = recommendation.winner_key
    for product in shortlist:
        product.recommended = product_key_for(product.model_dump()) == winner_key

    return shortlist, recommendation
