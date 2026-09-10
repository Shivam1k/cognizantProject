"""Pydantic request and response contracts exposed by the HTTP API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Review(BaseModel):
    """A single customer review scraped from a retailer page."""

    rating: float | None = None
    text: str = ""
    author: str = ""
    date: str = ""
    verified_purchase: bool = False
    source: str = ""


class QnA(BaseModel):
    """A customer question-and-answer pair scraped from a retailer page."""

    question: str
    answer: str = ""
    source: str = ""


class AttributeValue(BaseModel):
    """One category-agnostic extracted attribute, kept traceable to its source."""

    value: str
    source_snippet: str = ""


class Product(BaseModel):
    """A product normalized from a search result, PDF, or product page."""

    name: str
    brand: str = "Unknown"
    price: str = "Price unavailable"
    specs: dict[str, str] = Field(default_factory=dict)
    imageUrl: str = ""
    source: str = "Unknown"
    link: str = ""
    recommended: bool = False
    description: str = ""
    rating: float | None = None
    rating_count: int | None = None
    delivery: str = ""
    offers: str = ""
    product_id: str = ""
    position: int | None = None
    verified: bool = False
    verification_note: str = "Retailer page has not been verified."
    observed_price: str = ""

    # --- Deep-scrape / RAG additions ---
    category: str = ""
    attributes: dict[str, AttributeValue] = Field(default_factory=dict)
    reviews: list[Review] = Field(default_factory=list)
    qna: list[QnA] = Field(default_factory=list)
    review_summary: str = ""
    deep_scraped: bool = False


class ScoreBreakdown(BaseModel):
    """Transparent, weighted components behind one product's rule-based score."""

    price_score: float = 0.0
    rating_score: float = 0.0
    review_sentiment_score: float = 0.0
    feature_match_score: float = 0.0
    weights: dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0


class RecommendationItem(BaseModel):
    """One ranked product plus its transparent score and LLM justification."""

    product_key: str
    name: str
    rank: int
    score_breakdown: ScoreBreakdown
    justification: str = ""


class RecommendationResponse(BaseModel):
    """Full hybrid recommendation: rule-based ranking + LLM-written explanation."""

    winner_key: str = ""
    summary: str = ""
    items: list[RecommendationItem] = Field(default_factory=list)
    # Returned after an on-demand deep comparison so the client can render
    # the source-backed reviews, Q&A, and extracted attributes it just asked
    # for. Existing consumers can safely ignore this optional additive field.
    deep_products: list[Product] = Field(default_factory=list)


class DeepCompareRequest(BaseModel):
    """Request to deep-scrape, score, and justify a shortlist of products."""

    session_id: str
    products: list[Product] = Field(default_factory=list, max_length=12)
    priorities: dict[str, float] = Field(default_factory=dict)
    user_query: str = ""


class SessionResponse(BaseModel):
    """Response returned after creating a chat session."""

    session_id: str


class ChatRequest(BaseModel):
    """A user message submitted for a specific session."""

    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    selected_products: list[Product] = Field(default_factory=list, max_length=4)


class ChatResponse(BaseModel):
    """Grounded assistant reply and any products found during the turn."""

    response: str
    products: list[Product] = Field(default_factory=list)
    reasoning_depth: str = ""
    recommendation: RecommendationResponse | None = None
    active_product_keys: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Result of processing a product image or specification PDF."""

    response: str
    products: list[Product] = Field(default_factory=list)
    reasoning_depth: str = ""


class MessageResponse(BaseModel):
    """A persisted chat message returned by the history endpoint."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime | str
