"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

# Shared chat model for the LLM-backed tools.
_MODEL = "llama-3.3-70b-versatile"


def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Filter by price ceiling (inclusive) and size, if provided.
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]
    if size:
        size_norm = size.strip().lower()
        listings = [item for item in listings if _size_matches(size_norm, item["size"])]

    # 2. Score remaining listings by keyword overlap with the description.
    keywords = _extract_keywords(description)
    scored = []
    for item in listings:
        score = _score_listing(item, keywords)
        if score > 0:
            scored.append((score, item))

    # 3. Sort by score, highest first. (Stable sort keeps dataset order on ties.)
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# Common words that carry no search signal — dropped before scoring.
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "of", "to",
    "my", "me", "i", "looking", "under", "size", "some", "that",
    "this", "it", "is", "im",
}


def _size_matches(wanted: str, listing_size: str) -> bool:
    """
    True if `wanted` (already lowercased) matches the listing's size.

    Splits the listing size into whole tokens on spaces and slashes (keeping
    decimals like "8.5" intact), so:
        "m"   matches "S/M"       (tokens: s, m)
        "8"   matches "US 8"      (tokens: us, 8)
        "w30" matches "W30 L30"   (tokens: w30, l30)
        "8"   does NOT match "W28" or "US 8.5"  (no bare "8" token)
    """
    tokens = "".join(
        ch if ch.isalnum() or ch == "." else " " for ch in listing_size.lower()
    ).split()
    return wanted in tokens


def _extract_keywords(description: str) -> set[str]:
    """Lowercase the description and return its meaningful word tokens."""
    tokens = "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in description.lower()
    ).split()
    return {tok for tok in tokens if len(tok) > 1 and tok not in _STOP_WORDS}


def _score_listing(item: dict, keywords: set[str]) -> int:
    """
    Count how many query keywords appear in a listing's searchable fields.
    Title and style tags are weighted higher since they're the strongest signal.
    """
    if not keywords:
        return 0

    weighted_text = " ".join([
        item.get("title", ""),
        " ".join(item.get("style_tags", [])),   # weighted x2 below
        item.get("category", ""),
        " ".join(item.get("colors", [])),
        item.get("description", ""),
        item.get("brand") or "",
    ]).lower()

    strong_text = (
        item.get("title", "") + " " + " ".join(item.get("style_tags", []))
    ).lower()

    score = 0
    for kw in keywords:
        if kw in weighted_text:
            score += 1
        if kw in strong_text:   # bonus point for title/style-tag matches
            score += 1
    return score


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()
    item_desc = _format_item(new_item)
    items = wardrobe.get("items", [])

    if not items:
        # Empty-wardrobe branch: general styling advice, no specific pieces.
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They haven't entered any wardrobe pieces yet. Give general styling "
            "advice for this item: what kinds of pieces pair well with it, what "
            "vibe or occasions it suits, and one or two example outfit directions. "
            "Keep it to a short, friendly paragraph."
        )
    else:
        # Populated-wardrobe branch: combine the item with named owned pieces.
        wardrobe_text = "\n".join(f"- {_format_wardrobe_item(w)}" for w in items)
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Here is what they already own:\n{wardrobe_text}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces from their wardrobe. Refer to the owned pieces by name. Keep "
            "each outfit to 1-2 sentences and explain briefly why it works."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a thoughtful personal stylist who gives "
                           "concise, wearable outfit advice.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def _format_item(item: dict) -> str:
    """Compact one-line description of a listing for use in an LLM prompt."""
    parts = [
        item.get("title", "item"),
        f"category: {item.get('category', 'unknown')}",
        f"colors: {', '.join(item.get('colors', [])) or 'n/a'}",
        f"style: {', '.join(item.get('style_tags', [])) or 'n/a'}",
    ]
    return " | ".join(parts)


def _format_wardrobe_item(item: dict) -> str:
    """Compact one-line description of a wardrobe piece for an LLM prompt."""
    desc = f"{item.get('name', 'item')} ({item.get('category', 'unknown')}"
    colors = ", ".join(item.get("colors", []))
    if colors:
        desc += f", {colors}"
    return desc + ")"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "Couldn't create a fit card — no outfit suggestion was provided. "
            "Try generating an outfit first."
        )

    client = _get_groq_client()
    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"
    platform = new_item.get("platform", "secondhand")

    prompt = (
        f"Write a short, shareable caption for a thrifted outfit post.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Guidelines:\n"
        "- 2-4 sentences, casual and authentic like a real OOTD caption "
        "(not a product description).\n"
        f"- Mention the item name, the price ({price_str}), and the platform "
        f"({platform}) naturally, once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "- Just return the caption text, no preamble or quotation marks."
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You write punchy, authentic social-media captions "
                           "for secondhand fashion finds.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,   # higher temperature → more variety between runs
    )
    return response.choices[0].message.content.strip()


# ── Query parsing (planning-loop helper) ──────────────────────────────────────

def parse_query(query: str) -> dict:
    """
    Use the LLM to extract structured search parameters from a free-text query.

    Args:
        query: The shopper's natural-language request
               (e.g., "vintage graphic tee under $30, size M").

    Returns:
        A dict with keys:
            description (str):        the item keywords to search for
            size (str | None):        size to filter by, or None
            max_price (float | None): price ceiling, or None

    Never raises. If the LLM returns malformed JSON or anything goes wrong,
    falls back to {description: query, size: None, max_price: None} so the
    search step can still run.
    """
    fallback = {"description": query, "size": None, "max_price": None}

    prompt = (
        "Extract search parameters from this secondhand-clothing request and "
        "return ONLY a JSON object with keys \"description\", \"size\", and "
        "\"max_price\".\n"
        "- description: the item keywords to search for (string).\n"
        "- size: the requested size if stated, else null.\n"
        "- max_price: the price ceiling as a number if stated, else null.\n"
        "Do not include style/wardrobe context (like what they usually wear) "
        "in the description.\n\n"
        f"Request: {query}"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": "You extract structured data and reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
    except Exception:
        return fallback

    description = data.get("description") or query
    size = data.get("size") or None

    max_price = data.get("max_price")
    if isinstance(max_price, str):
        try:
            max_price = float(max_price.replace("$", "").strip())
        except ValueError:
            max_price = None
    elif not isinstance(max_price, (int, float)):
        max_price = None

    return {
        "description": str(description),
        "size": str(size) if size is not None else None,
        "max_price": float(max_price) if max_price is not None else None,
    }
