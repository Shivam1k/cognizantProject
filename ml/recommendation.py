"""Hybrid recommendation engine.

Two stages that stay separate and both visible to the user:

1. Rule-based scorer — normalizes price, rating, review sentiment, and
   attribute-match-to-user-intent into a weighted score per product. This is
   deterministic and produces a transparent, numeric, user-adjustable
   ranking.
2. LLM justifier — takes the ranked list plus the underlying evidence
   (specs, review snippets, Q&A) and writes the natural-language
   explanation. It never changes the ranking or invents a score — only
   explains one that already exists.
"""

from __future__ import annotations

import asyncio
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from backend.models import Product, RecommendationItem, RecommendationResponse, ScoreBreakdown
from backend.settings import GROQ_API_KEY, TEXT_MODEL
from database.database import product_key_for

DEFAULT_WEIGHTS = {
    "price": 0.30,
    "rating": 0.25,
    "review_sentiment": 0.20,
    "feature_match": 0.25,
}

_POSITIVE_WORDS = re.compile(
    r"\b(great|excellent|good|love|amazing|perfect|worth|reliable|comfortable|durable|fast|value)\b", re.I
)
_NEGATIVE_WORDS = re.compile(
    r"\b(bad|poor|terrible|broke|broken|waste|disappoint\w*|slow|uncomfortable|cheap(?:ly)?|defect\w*|issue|problem)\b",
    re.I,
)


def _price_to_number(price: str) -> float | None:
    digits = re.sub(r"[^\d.]", "", price or "")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _normalize(value: float, low: float, high: float, invert: bool = False) -> float:
    """Map a value into 0-1 given the observed range across candidates."""
    if high <= low:
        return 0.5
    score = (value - low) / (high - low)
    score = max(0.0, min(1.0, score))
    return 1.0 - score if invert else score


def _review_sentiment_score(product: Product) -> float:
    """Simple, explainable lexical sentiment over scraped review text (0-1)."""
    if not product.reviews:
        return 0.5  # neutral / unconfirmed, does not penalize products with no reviews yet
    positive = negative = 0
    for review in product.reviews:
        positive += len(_POSITIVE_WORDS.findall(review.text))
        negative += len(_NEGATIVE_WORDS.findall(review.text))
    total = positive + negative
    if total == 0:
        return 0.5
    return positive / total


def _feature_match_score(product: Product, user_query: str) -> float:
    """Overlap between the user's stated need and this product's dynamic attributes."""
    if not user_query.strip():
        return 0.5
    query_terms = {term for term in re.findall(r"[a-z0-9]+", user_query.lower()) if len(term) > 2}
    if not query_terms:
        return 0.5
    haystack = " ".join(
        [product.description, *(f"{k} {v.value}" for k, v in product.attributes.items()), *(f"{k} {v}" for k, v in product.specs.items())]
    ).lower()
    if not haystack.strip():
        return 0.5
    hits = sum(1 for term in query_terms if term in haystack)
    return min(1.0, hits / max(1, len(query_terms)))


def score_products(
    products: list[Product],
    user_query: str = "",
    weights: dict[str, float] | None = None,
) -> list[RecommendationItem]:
    """Deterministically rank products. Same inputs always produce the same ranking."""
    if not products:
        return []
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    weight_sum = sum(weights.values()) or 1.0
    weights = {key: value / weight_sum for key, value in weights.items()}

    prices = [p for p in (_price_to_number(product.price) for product in products) if p is not None]
    price_low, price_high = (min(prices), max(prices)) if prices else (0.0, 0.0)
    ratings = [product.rating for product in products if product.rating is not None]
    rating_low, rating_high = (min(ratings), max(ratings)) if ratings else (0.0, 5.0)

    items: list[RecommendationItem] = []
    for product in products:
        price_value = _price_to_number(product.price)
        price_score = _normalize(price_value, price_low, price_high, invert=True) if price_value is not None else 0.5
        rating_score = _normalize(product.rating, rating_low, rating_high) if product.rating is not None else 0.5
        review_score = _review_sentiment_score(product)
        feature_score = _feature_match_score(product, user_query)

        total = (
            weights["price"] * price_score
            + weights["rating"] * rating_score
            + weights["review_sentiment"] * review_score
            + weights["feature_match"] * feature_score
        )

        items.append(
            RecommendationItem(
                product_key=product_key_for(product.model_dump()),
                name=product.name,
                rank=0,
                score_breakdown=ScoreBreakdown(
                    price_score=round(price_score, 3),
                    rating_score=round(rating_score, 3),
                    review_sentiment_score=round(review_score, 3),
                    feature_match_score=round(feature_score, 3),
                    weights=weights,
                    total_score=round(total, 4),
                ),
            )
        )

    items.sort(key=lambda item: item.score_breakdown.total_score, reverse=True)
    for rank, item in enumerate(items, start=1):
        item.rank = rank
    return items


class Justification(BaseModel):
    winner_reason: str = Field(description="1-2 sentences on why the top-ranked product won, grounded in its scores/evidence.")
    per_product: dict[str, str] = Field(default_factory=dict, description="product name -> one short sentence explaining its rank/trade-off")


def _llm() -> ChatGroq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    return ChatGroq(api_key=GROQ_API_KEY, model=TEXT_MODEL, temperature=0.3, timeout=45, max_retries=1)


async def justify_ranking(
    products: list[Product],
    ranked: list[RecommendationItem],
    user_query: str = "",
) -> RecommendationResponse:
    """Ask the LLM to explain an already-computed ranking. It must not alter it."""
    if not ranked:
        return RecommendationResponse(summary="Not enough product evidence yet to recommend one.")

    by_key = {product_key_for(product.model_dump()): product for product in products}
    evidence_lines = []
    for item in ranked:
        product = by_key.get(item.product_key)
        if not product:
            continue
        review_note = f"{len(product.reviews)} scraped reviews" if product.reviews else "no scraped reviews"
        evidence_lines.append(
            f"- {product.name} | rank {item.rank} | total_score {item.score_breakdown.total_score} "
            f"(price {item.score_breakdown.price_score}, rating {item.score_breakdown.rating_score}, "
            f"review_sentiment {item.score_breakdown.review_sentiment_score}, feature_match {item.score_breakdown.feature_match_score}) "
            f"| price {product.price} | rating {product.rating} | {review_note}"
        )

    if not GROQ_API_KEY:
        winner = by_key.get(ranked[0].product_key)
        summary = f"My pick: {winner.name if winner else ranked[0].name} — highest weighted score among the compared products."
        for item in ranked:
            item.justification = f"Ranked #{item.rank} with a weighted score of {item.score_breakdown.total_score}."
        return RecommendationResponse(winner_key=ranked[0].product_key, summary=summary, items=ranked)

    prompt = (
        f"User's stated need: {user_query or '(not specified)'}\n\n"
        f"Already-computed, deterministic ranking (do NOT change the order or scores):\n"
        + "\n".join(evidence_lines)
        + "\n\nWrite a short reason the #1 product won, referencing its scores/evidence. "
        "Then write one short trade-off sentence for every OTHER product, explaining why it ranked lower "
        "(e.g. higher price, weaker reviews, missing a feature the user wants)."
    )
    try:
        result = await asyncio.to_thread(
            lambda: _llm().with_structured_output(Justification).invoke([
                SystemMessage(
                    content="You explain a ranking that was already computed by a deterministic scorer. "
                    "Never re-rank, never invent facts not present in the evidence given."
                ),
                HumanMessage(content=prompt),
            ])
        )
        for item in ranked:
            item.justification = result.per_product.get(item.name, "")
        summary = f"My pick: {ranked[0].name} — {result.winner_reason}".strip()
    except Exception:
        for item in ranked:
            item.justification = f"Ranked #{item.rank} with a weighted score of {item.score_breakdown.total_score}."
        summary = f"My pick: {ranked[0].name} — highest weighted score among the compared products."

    return RecommendationResponse(winner_key=ranked[0].product_key, summary=summary, items=ranked)


async def recommend(
    products: list[Product],
    user_query: str = "",
    weights: dict[str, float] | None = None,
) -> RecommendationResponse:
    """Score deterministically, then have the LLM justify (never re-rank) the result."""
    ranked = score_products(products, user_query, weights)
    return await justify_ranking(products, ranked, user_query)
