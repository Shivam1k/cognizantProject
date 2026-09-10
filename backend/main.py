"""FastAPI entrypoint for the ProductGenie comparison assistant."""

import io
import uuid
from contextlib import asynccontextmanager

import pdfplumber
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.models import (
    ChatRequest,
    ChatResponse,
    DeepCompareRequest,
    MessageResponse,
    RecommendationResponse,
    SessionResponse,
    UploadResponse,
)
from database.database import create_session, get_history, get_session_product_name, initialize_database, session_exists
from ml.graph import build_graph
from ml.pipeline import deep_compare


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize durable storage once before accepting requests."""
    initialize_database()
    yield


app = FastAPI(title="ProductGenie API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Vite may use a fallback port (5174, 5175, …), and may be opened using
    # either local hostname during development.
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
graph = build_graph()


def _require_session(session_id: str) -> None:
    """Raise a useful HTTP error when a request uses an unknown session id."""
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found. Create a session first.")


@app.post("/session", response_model=SessionResponse, summary="Create a persistent chat session")
async def create_chat_session() -> SessionResponse:
    """Create and return a UUID used to persist the user's conversation history."""
    session_id = str(uuid.uuid4())
    create_session(session_id)
    return SessionResponse(session_id=session_id)


@app.post("/chat", response_model=ChatResponse, summary="Search, compare, or follow up through the LangGraph flow")
async def chat(request: ChatRequest) -> ChatResponse:
    """Run a natural-language turn and return a grounded reply plus active products."""
    _require_session(request.session_id)
    try:
        result = await graph.ainvoke({
            "session_id": request.session_id,
            "user_query": request.message,
            "product_name": get_session_product_name(request.session_id),
            "chat_history": get_history(request.session_id),
            "selected_products": request.selected_products,
        })
        return ChatResponse(
            response=result["response"],
            products=result.get("products", []),
            reasoning_depth=result.get("reasoning_depth", ""),
            recommendation=result.get("recommendation"),
            active_product_keys=result.get("active_product_keys", []),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Product assistant is temporarily unavailable: {exc}") from exc


@app.post(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Deep-scrape a shortlist and return a scored, justified recommendation",
)
async def recommend(request: DeepCompareRequest) -> RecommendationResponse:
    """On-demand deep comparison for the Analytics page's 'Why this pick' panel."""
    _require_session(request.session_id)
    if not request.products:
        raise HTTPException(status_code=400, detail="Provide at least one product to compare.")
    try:
        deep_products, recommendation = await deep_compare(
            request.session_id, request.products, request.user_query, request.priorities
        )
        recommendation.deep_products = deep_products
        return recommendation
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Recommendation engine is temporarily unavailable: {exc}") from exc


@app.post("/upload-photo", response_model=UploadResponse, summary="Identify a product photo and find similar listings")
async def upload_photo(session_id: str, file: UploadFile = File(...)) -> UploadResponse:
    """Send an uploaded image through Groq vision and Serper Shopping search."""
    _require_session(session_id)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Please upload an image file.")
    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload an image smaller than 4 MB.")
    try:
        result = await graph.ainvoke({"session_id": session_id, "user_query": "Review this product", "image_bytes": data, "image_mime_type": file.content_type, "product_name": get_session_product_name(session_id), "chat_history": get_history(session_id)})
        return UploadResponse(
            response=result["response"], products=result.get("products", []), reasoning_depth=result.get("reasoning_depth", "")
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Photo identification failed: {exc}") from exc


@app.post("/upload-pdf", response_model=UploadResponse, summary="Parse a product specification PDF")
async def upload_pdf(session_id: str, file: UploadFile = File(...)) -> UploadResponse:
    """Extract PDF text with pdfplumber and add the parsed product to the session index."""
    _require_session(session_id)
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=415, detail="Please upload a PDF file.")
    try:
        data = await file.read()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            raw_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        result = await graph.ainvoke({"session_id": session_id, "user_query": "Analyze uploaded PDF spec sheet", "pdf_text": raw_text, "product_name": get_session_product_name(session_id), "chat_history": get_history(session_id)})
        return UploadResponse(
            response=result["response"], products=result.get("products", []), reasoning_depth=result.get("reasoning_depth", "")
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse this PDF: {exc}") from exc


@app.get("/history/{session_id}", response_model=list[MessageResponse], summary="Get a session's complete chat history")
async def history(session_id: str) -> list[MessageResponse]:
    """Return ordered persisted user and assistant messages for a valid session."""
    _require_session(session_id)
    return [MessageResponse(**item) for item in get_history(session_id)]
