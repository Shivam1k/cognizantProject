"""LangGraph orchestration for ProductGenie's conversational workflows."""

import base64
import re
from typing import Literal, TypedDict

import pdfplumber
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from backend.models import Product, RecommendationResponse
from backend.settings import GROQ_API_KEY, TEXT_MODEL, VISION_MODEL
from database.database import (
    get_active_products,
    get_history,
    get_products as get_stored_products,
    product_key_for,
    save_message,
    set_active_products,
    set_session_product_name,
)
from ml.pipeline import deep_compare
from ml.services import compact_products, enrich_products, lowest_verified_offer, product_from_pdf_text, search_shopping, vector_store


SYSTEM_PROMPT = """You are ProductGenie: a warm, decisive shopping companion, not a report writer.

Use ONLY supplied product facts. Never infer typical specs, expected performance, brand reputation, or prices. Do not use “likely”, “typically”, “often”, or claims about what a product line is known for. If a fact is missing, say it is unconfirmed.

Reply in 70–130 words. Do not use markdown tables, headings, long checklists, or preambles. Use this natural format:
• Start with “My pick: [product] — [price] ([source]).” and give one evidence-based reason.
• Mention up to two alternatives with a clear trade-off each.
• Add one brief “Check before buying” note only when a decision-critical fact is unavailable.
• End with exactly one friendly, relevant question that helps narrow the choice (for example, workload, family size, preferred type, portability, or a priority).

If the user asks a follow-up, answer it directly using products already in the session, then ask one useful next question. Keep the tone conversational, confident, and practical."""


SYSTEM_PROMPT = """You are ProductGenie, a thoughtful shopping advisor who remembers the conversation.

Grounding is non-negotiable: use ONLY the trusted product data and chat history supplied. Never invent or infer specs, prices, performance, seller details, or brand reputation. Say a decision-critical fact is unconfirmed when it is absent.

Do not repeat the same response structure for every turn. Match your format to what is being asked and remember the user's prior messages like a human salesperson. For "compare the top two", discuss exactly those products in focused prose, cite concrete facts, and name the single deciding factor. For "best value", answer directly from known price and explicitly available spec tier; do not re-list every product. When the user changes a priority, acknowledge that shift before re-ranking; if the new priority is missing, ask for it instead of re-answering with the old data. Casual follow-ups should be short and conversational.

Match the response shape to the user's request; do not repeat one template. For a first search, give a clear recommendation with one or two alternatives and concise reasoning. For a comparison request, discuss exactly the relevant products in natural side-by-side prose and name the deciding factor. For a best-value question, answer directly using the known price and explicitly available spec tier; do not re-list everything. For a priority-change request, acknowledge the shift and re-rank using that priority. For a vague or casual follow-up, be brief and conversational.

Reference earlier needs naturally when they matter. Explain why a known fact matters to the stated use case rather than merely repeating it. Do not use the repeated labels “My pick:”, “Alternative 1:”, or “Check before buying:” except when a first full recommendation genuinely benefits from them. Ask a follow-up question only if its answer could change the recommendation and it was not already answered in the history. Keep most replies under 150 words; use no markdown tables."""


ACCURACY_SYSTEM_PROMPT = """You are ProductGenie, a careful shopping advisor who remembers the full conversation.

Grounding is absolute: make claims only from the supplied chat history and trusted product records. Never invent or infer specifications, ingredients, performance, compatibility, prices, seller information, availability, reviews, or brand reputation. If a relevant field is absent, call it unconfirmed. A lower price is never, by itself, proof that a product is better value.

First identify the user's real priority from their current message and earlier messages. Then compare the product-specific fields that are actually available. Use category-appropriate evidence only when it is explicitly present: for example, capacity, energy rating, or modes for appliances; processor, RAM, storage, display, or battery for computers; form, declared ingredients, strength, quantity, or serving count for supplements; and dimensions, material, or weight for furniture. Do not assume that any field exists because it is normal for that product category.

When verified UI-selected listings are supplied, treat them as the user's current focus for an otherwise vague follow-up. Do not switch categories merely because the user repeats a listing title from the current results.

For a recommendation, explain the feature-to-need connection before discussing price. When candidates are close, name the one confirmed feature or price difference that decides the outcome. For a comparison request, discuss exactly the requested or selected products feature by feature, including meaningful differences and missing details. For best value, weigh the known feature differences against price and say when evidence is too incomplete for a value verdict. If a priority changes, acknowledge the shift and re-rank according to it.

For a first product search, the first trusted record is the lowest currently verified retailer offer when it has a price. State its retailer, but never include a source URL or any other link in the visible response. Never replace it with an inferred or unavailable price.

Vary response shape with the request. A first search may include a clear pick and alternatives; follow-ups should be direct, natural prose. Do not reuse labels such as “My pick,” “Alternative 1,” or “Check before buying” on every turn. Ask a question only if its answer could change the recommendation and history has not already answered it. Keep the visible response concise, warm, and under 160 words; do not use markdown tables.

Use lightweight line-based structure in every visible response: begin with one short lead sentence, then place the recommendation and each meaningful alternative on its own line, prefixed with a bullet. Keep each bullet concise and grounded in the supplied facts. Use plain line breaks and bullet characters; do not add headings, tables, or extra sections."""


class GraphState(TypedDict, total=False):
    """State carried between intent, tool, retrieval, and response nodes."""

    session_id: str
    user_query: str
    intent: Literal["search", "compare", "photo", "pdf", "followup"]
    chat_history: list[dict]
    products: list[Product]
    product_name: str
    response: str
    reasoning_depth: str
    pdf_text: str
    image_bytes: bytes
    image_mime_type: str
    selected_products: list[Product]
    matched_products: list[Product]
    recommendation: RecommendationResponse | None
    active_product_keys: list[str]
    grounding_chunks: list[str]


class IntentClassification(BaseModel):
    """Schema returned by Groq for selecting a LangGraph route."""

    intent: Literal["search", "compare", "photo", "pdf", "followup"]


class ProductExtraction(BaseModel):
    """Structured, source-preserving product extraction result from Groq."""

    products: list[Product]


class AdvisorResponse(BaseModel):
    """Grounded reply plus a compact explanation for the UI disclosure."""

    response: str
    reasoning_depth: str = ""


def _llm(model: str = TEXT_MODEL) -> ChatGroq:
    """Create the Groq LangChain chat client for a configured model."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    return ChatGroq(api_key=GROQ_API_KEY, model=model, temperature=0.2, timeout=45, max_retries=1)


def classify_intent_node(state: GraphState) -> dict:
    """Classify the request with Groq, falling back to deterministic routing if unavailable."""
    query = state["user_query"].lower()
    product_name = state.get("product_name", "")
    if state.get("image_bytes"):
        intent = "photo"
    elif state.get("pdf_text"):
        intent = "pdf"
    elif any(word in query for word in ("compare", "versus", " vs ", "difference", "which one", "top two", "best value", "worth it")):
        intent = "compare"
    elif any(word in query for word in ("what if", "instead", "battery", "more important", "cheaper", "follow", "priority", "thanks", "thank you")):
        intent = "followup"
    else:
        intent = "search"
    if product_name and not state.get("image_bytes") and not state.get("pdf_text") and intent != "compare":
        # A listing title typed back into the chat refers to existing results;
        # any other product request remains a fresh search in this same session.
        matched = vector_store.named(state["session_id"], state["user_query"])
        if matched:
            return {"intent": "followup", "matched_products": matched}

    if product_name and GROQ_API_KEY and not state.get("image_bytes") and not state.get("pdf_text"):
        try:
            classifier = _llm().with_structured_output(IntentClassification)
            result = classifier.invoke([
                SystemMessage(content=f"The most recent product search was: {product_name}. This conversation can include multiple product categories. Classify the request as exactly one of search, compare, or followup. Use search whenever the user asks to find, review, analyze, identify, upload, or switch to a product category. Use compare/followup only when it is about previously retrieved listings."),
                HumanMessage(content=state["user_query"]),
            ])
            intent = result.intent
        except Exception:
            # The graph can still route clear requests when a provider is temporarily unavailable.
            pass
    return {"intent": intent}


def load_chat_history_node(state: GraphState) -> dict:
    """Load persisted messages to give follow-up replies full session context."""
    return {"chat_history": get_history(state["session_id"])}


def vision_identify_node(state: GraphState) -> dict:
    """Use Groq vision to identify a pictured product and turn it into a shopping query."""
    encoded = base64.b64encode(state["image_bytes"]).decode("ascii")
    mime_type = state.get("image_mime_type", "image/jpeg")
    message = HumanMessage(content=[
        {"type": "text", "text": "Classify the largest central object into the safest common shopping category. Reply with ONLY a 2–4 word shopping phrase: for example 'office chair', 'dining chair', 'gaming chair', 'wireless headphones', or 'front load washing machine'. Do not describe the scene, guess a brand/model, add an explanation, or use punctuation. A seat with a backrest, legs, armrests, or caster wheels is a chair/furniture item—not an appliance. Only call something an appliance when controls, a door, vents, or a power connection are visibly clear. If unsure, use the broadest safe category."},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
    ])
    identification = _llm(VISION_MODEL).invoke([message]).content
    # Serper Shopping requires a compact plain-text query. Vision responses can
    # otherwise contain formatting or multi-line descriptions that it rejects.
    search_query = re.sub(r"[^A-Za-z0-9 .&+_-]", " ", str(identification))
    search_query = re.sub(r"\s+", " ", search_query).strip()[:120]
    if not search_query:
        search_query = "product shown in photo"
    return {"user_query": search_query, "response": f"I identified this as: {search_query}"}


def live_search_node(state: GraphState) -> dict:
    """Resolve up to eight listings for a search in the current conversation."""
    return {"products": search_shopping(state["user_query"])[:8]}


def parse_pdf_node(state: GraphState) -> dict:
    """Convert supplied PDF text into one conservative product record for comparison."""
    product = product_from_pdf_text(state.get("pdf_text", ""))
    return {"products": [product]}


def extract_specs_node(state: GraphState) -> dict:
    """Keep source-labeled specs unchanged; never let an LLM swap numeric fields."""
    return {"products": state.get("products", [])}


async def enrich_products_node(state: GraphState) -> dict:
    """Deepen every candidate so comparison is not driven by price alone."""
    products = state.get("products", [])
    return {"products": await enrich_products(products)}


def embed_and_store_node(state: GraphState) -> dict:
    """Embed current listings, retain search context, and reset the active product set.

    A fresh search always resets the "working memory" pointer used by
    follow-ups — this is the "start a new search" boundary the active set
    only resets on.
    """
    products = state.get("products", [])
    if products:
        category = products[0].name if state.get("intent") == "pdf" else state["user_query"]
        set_session_product_name(state["session_id"], category)
    vector_store.add(state["session_id"], products)
    keys = [product_key_for(product.model_dump()) for product in products]
    if keys:
        set_active_products(state["session_id"], keys, intent=state.get("intent", "search"))
    return {"products": products, "active_product_keys": keys}


def retrieve_products_node(state: GraphState) -> dict:
    """Honor user-selected listings, then fill context from the complete session index."""
    try:
        selected = vector_store.selected(state["session_id"], state.get("selected_products", []))
        retrieved = vector_store.search(state["session_id"], state["user_query"], limit=8)
    except Exception:
        selected = list(state.get("selected_products", []))
        retrieved = []
        for record in get_stored_products(state["session_id"]):
            try:
                retrieved.append(Product.model_validate(record))
            except Exception:
                continue
    selected_keys = {(product.name, product.price, product.source, product.link) for product in selected}
    products = [*selected, *(product for product in retrieved if (product.name, product.price, product.source, product.link) not in selected_keys)]
    return {"products": products}


def rerank_node(state: GraphState) -> dict:
    """Scope a follow-up to the session's active product set — the "working memory"
    pointer — instead of re-searching the whole session on every question.

    If the user has narrowed to a handful of products (via search, selection,
    or a comparison), follow-ups like "which has the best graphics?" stay
    scoped to exactly those products until a new search resets the set.
    """
    matched = state.get("matched_products", [])
    if matched:
        keys = [product_key_for(product.model_dump()) for product in matched]
        return {"products": matched, "active_product_keys": keys}

    session_id = state["session_id"]
    all_session_products: list[Product] = []
    for record in get_stored_products(session_id):
        try:
            all_session_products.append(Product.model_validate(record))
        except Exception:
            continue

    active_keys = get_active_products(session_id)
    scoped = [product for product in all_session_products if product_key_for(product.model_dump()) in active_keys] if active_keys else []

    if scoped:
        products = scoped
    else:
        # No active set yet (e.g. first follow-up in a session) — fall back
        # to whole-session semantic retrieval, same as before.
        try:
            selected = vector_store.selected(session_id, state.get("selected_products", []))
            retrieved = vector_store.search(session_id, state["user_query"], limit=8)
        except Exception:
            selected = []
            retrieved = all_session_products
        selected_keys = {(product.name, product.price, product.source, product.link) for product in selected}
        products = [*selected, *(product for product in retrieved if (product.name, product.price, product.source, product.link) not in selected_keys)]
        products = products or state.get("products", [])

    grounding_chunks: list[str] = []
    if products:
        keys = [product_key_for(product.model_dump()) for product in products]
        try:
            grounding_chunks = vector_store.search_chunks(session_id, state["user_query"], keys, limit=8)
        except Exception:
            grounding_chunks = []

    return {"products": products, "grounding_chunks": grounding_chunks}


async def compare_node(state: GraphState) -> dict:
    """Deep-scrape the shortlist, then run the hybrid rule-based + LLM recommendation.

    This narrows the active product set to exactly the products being
    compared, so subsequent follow-up questions in this turn's context stay
    scoped to them until the user starts a new search.
    """
    products = state.get("products", [])
    if not products:
        return {"products": products}
    try:
        enriched, recommendation = await deep_compare(state["session_id"], products, state.get("user_query", ""))
        keys = [product_key_for(product.model_dump()) for product in enriched]
        set_active_products(state["session_id"], keys, intent="compare")
        return {"products": enriched, "recommendation": recommendation, "active_product_keys": keys}
    except Exception:
        # Deep comparison is an enhancement; a failure here should not break
        # the turn — fall back to a plain top-of-list recommendation.
        if products:
            products[0].recommended = True
        return {"products": products}


def respond_node(state: GraphState) -> dict:
    """Generate a grounded natural-language response from products and persisted context."""
    products = state.get("products", [])
    if not products:
        return {
            "response": "I don't have enough product data in this session yet. Try a product search or upload a spec sheet.",
            "reasoning_depth": "No trusted products are available in this session yet.",
        }
    # Keep the whole conversation available so an earlier budget or priority is not lost.
    history = "\n".join(f"{m['role']}: {m['content']}" for m in state.get("chat_history", [])) or "(This is the first turn.)"
    selected = vector_store.selected(state["session_id"], state.get("selected_products", []))
    selected_context = compact_products(selected) if selected else "(No verified UI selection.)"
    recommendation = state.get("recommendation")
    recommendation_context = (
        f"Deterministic scored ranking + justification (already computed, ground your answer in it):\n"
        f"{recommendation.model_dump_json()}\n\n"
        if recommendation else ""
    )
    grounding_chunks = state.get("grounding_chunks") or []
    grounding_context = (
        "Grounding evidence retrieved from deep-scraped reviews/specs/Q&A for the products currently in focus:\n"
        + "\n".join(f"- {chunk}" for chunk in grounding_chunks) + "\n\n"
        if grounding_chunks else ""
    )
    prompt = (
        f"Conversation route: {state.get('intent', 'search')}\n"
        f"Current user request: {state['user_query']}\n"
        f"Full chat history:\n{history}\n\n"
        f"Verified UI-selected listings (the current focus when relevant):\n{selected_context}\n\n"
        f"{recommendation_context}"
        f"{grounding_context}"
        f"Trusted product data:\n{compact_products(products)}\n\n"
        "Return a concise visible answer and a separate one-sentence reasoning_depth. "
        "reasoning_depth must contain only the key grounded deciding factor, or be empty."
    )
    try:
        answer = _llm().with_structured_output(AdvisorResponse).invoke([
            SystemMessage(content=ACCURACY_SYSTEM_PROMPT), HumanMessage(content=prompt)
        ])
        response = answer.response
        lowest_offer = lowest_verified_offer(products)
        if state.get("intent") in {"search", "photo", "pdf"} and lowest_offer:
            response = (
                f"Lowest live price: {lowest_offer.price} at {lowest_offer.source}.\n\n"
                f"{response}"
            )
        # URLs make chat bubbles overflow on small screens. Source links stay
        # available on Current results cards, so remove any model-generated
        # link from the chat text as a final safeguard.
        response = re.sub(r"https?://\S+", "", response).strip()
        return {"response": response, "reasoning_depth": answer.reasoning_depth}
    except Exception:
        # Retain a usable chat when a provider/model does not support structured output.
        answer = _llm().invoke([SystemMessage(content=ACCURACY_SYSTEM_PROMPT), HumanMessage(content=prompt)]).content
        return {"response": re.sub(r"https?://\S+", "", str(answer)).strip(), "reasoning_depth": ""}


def save_to_sqlite_node(state: GraphState) -> dict:
    """Persist the user query and graph-generated assistant response at the end of every turn."""
    save_message(state["session_id"], "user", state["user_query"])
    save_message(state["session_id"], "assistant", state.get("response", ""))
    return {}


def _route_after_intent(state: GraphState) -> str:
    """Return the next node name corresponding to the classified intent."""
    return state["intent"]


def build_graph():
    """Build and compile the ProductGenie LangGraph state machine."""
    flow = StateGraph(GraphState)
    flow.add_node("classify_intent", classify_intent_node)
    flow.add_node("load_chat_history", load_chat_history_node)
    flow.add_node("vision_identify", vision_identify_node)
    flow.add_node("live_search", live_search_node)
    flow.add_node("parse_pdf", parse_pdf_node)
    flow.add_node("enrich_products", enrich_products_node)
    flow.add_node("extract_specs", extract_specs_node)
    flow.add_node("embed_and_store", embed_and_store_node)
    flow.add_node("retrieve_products", retrieve_products_node)
    flow.add_node("rerank", rerank_node)
    flow.add_node("compare", compare_node)
    flow.add_node("respond", respond_node)
    flow.add_node("save_to_sqlite", save_to_sqlite_node)
    flow.add_edge(START, "classify_intent")
    flow.add_conditional_edges("classify_intent", _route_after_intent, {
        "search": "live_search", "compare": "retrieve_products", "photo": "vision_identify", "pdf": "parse_pdf", "followup": "load_chat_history",
    })
    flow.add_edge("vision_identify", "live_search")
    flow.add_edge("live_search", "enrich_products")
    flow.add_edge("enrich_products", "extract_specs")
    flow.add_edge("parse_pdf", "extract_specs")
    flow.add_edge("extract_specs", "embed_and_store")
    flow.add_edge("embed_and_store", "respond")
    flow.add_edge("retrieve_products", "compare")
    flow.add_edge("compare", "respond")
    flow.add_edge("load_chat_history", "rerank")
    flow.add_edge("rerank", "respond")
    flow.add_edge("respond", "save_to_sqlite")
    flow.add_edge("save_to_sqlite", END)
    return flow.compile()
