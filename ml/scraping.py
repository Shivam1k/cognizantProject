"""Deep product-page scraping: reviews and Q&A, on top of the existing static scraper.

Two-tier fetch strategy
------------------------
Tier 1 (existing, ml.services.scrape_page_details): plain httpx + BeautifulSoup.
Cheap and fast, and enough for title/price/description/specs on most retailers.

Tier 2 (this module): reviews and Q&A are usually injected by JavaScript after
the page loads (infinite scroll, "load more reviews" buttons, AJAX widgets).
A plain GET request misses them, so this module uses Playwright to open a
real (headless) browser, wait for the content to render, then extract it.
Playwright is optional: if it is not installed, or USE_PLAYWRIGHT=false, the
generic static-HTML adapter still tries to pull whatever review/Q&A markup
already exists in the initial HTML (works on some sites, not all).

Per-domain adapter pattern
---------------------------
Every retailer marks up reviews and Q&A differently, so a single generic
parser cannot handle all of them well. Each adapter implements the same
interface (extract_reviews / extract_qna) and is looked up by domain, with a
generic fallback for anything unrecognized. One broken selector only breaks
one retailer's adapter, never the whole pipeline.
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.settings import USE_PLAYWRIGHT

try:  # Playwright's browser binary is a large optional install.
    from playwright.async_api import async_playwright

    _PLAYWRIGHT_IMPORTABLE = True
except ImportError:  # pragma: no cover - exercised only when not installed
    _PLAYWRIGHT_IMPORTABLE = False


USER_AGENT = "Mozilla/5.0 (compatible; ProductGenie/1.0; +deep-scrape)"

# Max concurrent requests aimed at any single retailer domain, so a
# multi-product comparison does not look like a scraping attack.
_PER_DOMAIN_SEMAPHORES: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(3))


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _rating_from_text(text: str) -> float | None:
    match = re.search(r"(\d(?:\.\d)?)\s*(?:out of|/)\s*5", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------

class BaseAdapter:
    """Default (generic) adapter: heuristic selectors that work reasonably
    across many storefronts, plus JSON-LD Review objects when present."""

    review_selectors = [
        "[data-hook='review']", ".review", ".reviewContent", "[itemprop='review']",
        "li.review-item", "div.review-item", "[class*='review-card']",
    ]
    qna_selectors = [
        "[data-hook='question-answer']", ".qna-item", ".question-answer",
        "[class*='qna']", "[class*='faq-item']",
    ]

    def extract_reviews(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        for selector in self.review_selectors:
            for node in soup.select(selector)[:20]:
                text = _text(node)
                if len(text) < 15:
                    continue
                reviews.append({
                    "text": text[:1000],
                    "rating": _rating_from_text(text),
                    "verified_purchase": bool(re.search(r"verified purchase", text, re.I)),
                })
            if reviews:
                break
        if not reviews:
            reviews.extend(self._reviews_from_json_ld(soup))
        return reviews[:25]

    def extract_qna(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        qna: list[dict[str, Any]] = []
        for selector in self.qna_selectors:
            for node in soup.select(selector)[:15]:
                text = _text(node)
                if "?" not in text or len(text) < 10:
                    continue
                question, _, answer = text.partition("?")
                qna.append({"question": f"{question.strip()}?", "answer": answer.strip()[:600]})
            if qna:
                break
        return qna[:15]

    @staticmethod
    def _reviews_from_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
        import json as _json

        reviews: list[dict[str, Any]] = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(tag.string or "")
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_reviews = item.get("review") or item.get("reviews") or []
                if isinstance(raw_reviews, dict):
                    raw_reviews = [raw_reviews]
                for entry in raw_reviews:
                    if not isinstance(entry, dict):
                        continue
                    body = str(entry.get("reviewBody", "")).strip()
                    if not body:
                        continue
                    rating = None
                    rating_obj = entry.get("reviewRating")
                    if isinstance(rating_obj, dict):
                        try:
                            rating = float(rating_obj.get("ratingValue"))
                        except (TypeError, ValueError):
                            rating = None
                    reviews.append({
                        "text": body[:1000],
                        "rating": rating,
                        "author": str((entry.get("author") or {}).get("name", "")) if isinstance(entry.get("author"), dict) else str(entry.get("author", "")),
                    })
        return reviews


class AmazonAdapter(BaseAdapter):
    review_selectors = ["[data-hook='review']", "div.a-section.review"]
    qna_selectors = ["[data-hook='question-answer']", "div.a-section.question"]


class FlipkartAdapter(BaseAdapter):
    review_selectors = ["div._27M-vq", "div.col._2wzgFH", "div._6K-7Co"]
    qna_selectors = ["div._2n62co", "div.qna-item"]


_ADAPTERS: dict[str, BaseAdapter] = {
    "amazon.in": AmazonAdapter(),
    "amazon.com": AmazonAdapter(),
    "flipkart.com": FlipkartAdapter(),
}
_GENERIC_ADAPTER = BaseAdapter()


def _adapter_for(url: str) -> BaseAdapter:
    domain = _domain(url)
    for key, adapter in _ADAPTERS.items():
        if key in domain:
            return adapter
    return _GENERIC_ADAPTER


# --------------------------------------------------------------------------
# Fetch tiers
# --------------------------------------------------------------------------

async def _fetch_static_html(url: str) -> str:
    """Tier 1: plain GET, no JS execution. Fast, cheap, misses lazy content."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def _fetch_rendered_html(url: str) -> str:
    """Tier 2: headless-browser fetch so JS-injected reviews/Q&A actually render.

    Only used when Playwright is installed and enabled; falls back to an
    empty string on any failure so the caller can fall back to Tier 1 data.
    """
    if not (_PLAYWRIGHT_IMPORTABLE and USE_PLAYWRIGHT):
        return ""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=USER_AGENT)
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                # Give lazy-loaded review/Q&A widgets a moment to render, and
                # nudge them into view since many sites only fetch on scroll.
                try:
                    await page.mouse.wheel(0, 2400)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
                html = await page.content()
                return html
            finally:
                await browser.close()
    except Exception:
        return ""


async def deep_scrape_product(url: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch and extract reviews + Q&A for a single product URL.

    Politely rate-limited per domain. Returns {} content on any failure —
    the caller treats missing evidence as "unconfirmed", never as an error
    that should break the rest of the comparison.
    """
    if not url:
        return {"reviews": [], "qna": []}

    domain = _domain(url)
    semaphore = _PER_DOMAIN_SEMAPHORES[domain]

    async with semaphore:
        # Small politeness delay so repeat requests to one retailer are spaced out.
        await asyncio.sleep(0.3)

        html = ""
        try:
            html = await _fetch_rendered_html(url)
        except Exception:
            html = ""

        if not html:
            try:
                html = await _fetch_static_html(url)
            except httpx.HTTPError:
                return {"reviews": [], "qna": []}

    soup = BeautifulSoup(html, "html.parser")
    adapter = _adapter_for(url)
    try:
        reviews = adapter.extract_reviews(soup)
    except Exception:
        reviews = []
    try:
        qna = adapter.extract_qna(soup)
    except Exception:
        qna = []

    for entry in reviews:
        entry.setdefault("source", domain)
    for entry in qna:
        entry.setdefault("source", domain)

    return {"reviews": reviews, "qna": qna}


async def deep_scrape_many(urls: list[str]) -> list[dict[str, list[dict[str, Any]]]]:
    """Deep-scrape several product URLs concurrently (per-domain limits still apply)."""
    return await asyncio.gather(*(deep_scrape_product(url) for url in urls))
