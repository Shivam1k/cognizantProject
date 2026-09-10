"""Category-agnostic attribute extraction.

The original extractor (ml.services.extract_specs_from_source_text) looks for
a hardcoded field list (RAM, storage, battery, camera...), which only works
for electronics. Since ProductGenie now compares any product category (shoes,
blenders, furniture, supplements...), extraction happens in two LLM steps:

1. Classify the product into a short category label.
2. Extract whatever attributes actually appear in the scraped evidence for
   that category — no fixed schema — as {attribute: {value, source_snippet}}
   pairs, so every fact stays traceable to the text it came from and the
   system never invents a value that wasn't in the evidence.
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from backend.models import AttributeValue, Product
from backend.settings import GROQ_API_KEY, TEXT_MODEL


class CategoryClassification(BaseModel):
    category: str = Field(description="A short, general shopping category, e.g. 'running shoes', 'blender', 'sofa'.")


class ExtractedAttribute(BaseModel):
    name: str
    value: str
    source_snippet: str = ""


class AttributeExtraction(BaseModel):
    attributes: list[ExtractedAttribute] = Field(default_factory=list)


def _llm() -> ChatGroq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    return ChatGroq(api_key=GROQ_API_KEY, model=TEXT_MODEL, temperature=0.1, timeout=45, max_retries=1)


async def classify_category(product: Product) -> str:
    """Return a short category label so extraction and scoring can adapt to it."""
    if not GROQ_API_KEY:
        return ""
    prompt = f"Product title: {product.name}\nBrand: {product.brand}\nExisting specs: {product.specs}"
    try:
        result = await asyncio.to_thread(
            lambda: _llm().with_structured_output(CategoryClassification).invoke([
                SystemMessage(content="Classify the shopping category in 1-3 words, lowercase, generic (not brand-specific)."),
                HumanMessage(content=prompt),
            ])
        )
        return result.category.strip().lower()
    except Exception:
        return ""


async def extract_dynamic_attributes(product: Product, evidence_text: str) -> dict[str, AttributeValue]:
    """Pull whatever attributes actually appear in scraped evidence, tied to their source text.

    Never invents a value: the LLM is instructed to only report attributes it
    can point to a snippet for, mirroring the existing "never guess missing
    specs" principle used for the fixed-field extractor.
    """
    if not GROQ_API_KEY or not evidence_text.strip():
        return {}

    category = product.category or "product"
    prompt = (
        f"Category: {category}\n"
        f"Product: {product.name}\n\n"
        f"Evidence text (description, page content, reviews, Q&A):\n{evidence_text[:8000]}\n\n"
        "Extract every concrete attribute explicitly stated in the evidence "
        "that matters for comparing products in this category (for example: "
        "material, dimensions, capacity, wattage, cushioning, ingredients, "
        "compatibility — whatever is actually present, do not force a fixed "
        "list). For each attribute give the short value and the exact "
        "snippet of evidence text it came from. Skip anything not explicitly "
        "stated; never infer or estimate a value."
    )
    try:
        result = await asyncio.to_thread(
            lambda: _llm().with_structured_output(AttributeExtraction).invoke([
                SystemMessage(content="You extract only explicitly stated product attributes, each traceable to a source snippet. Never guess."),
                HumanMessage(content=prompt),
            ])
        )
        attributes: dict[str, AttributeValue] = {}
        for item in result.attributes[:20]:
            name = item.name.strip()
            if not name or not item.value.strip():
                continue
            attributes[name] = AttributeValue(value=item.value.strip(), source_snippet=item.source_snippet.strip()[:300])
        return attributes
    except Exception:
        return {}


async def enrich_with_dynamic_attributes(products: list[Product]) -> list[Product]:
    """Classify category and extract dynamic attributes for a shortlist of products."""
    categories = await asyncio.gather(*(classify_category(product) for product in products))
    for product, category in zip(products, categories):
        if category:
            product.category = category

    async def _for_one(product: Product) -> dict[str, AttributeValue]:
        evidence = "\n".join([
            product.description,
            "\n".join(f"Review: {review.text}" for review in product.reviews[:15]),
            "\n".join(f"Q: {qa.question} A: {qa.answer}" for qa in product.qna[:15]),
        ])
        return await extract_dynamic_attributes(product, evidence)

    attribute_sets = await asyncio.gather(*(_for_one(product) for product in products))
    for product, attributes in zip(products, attribute_sets):
        if attributes:
            product.attributes = attributes
    return products
