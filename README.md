# FitFindr 🛍️

A multi-tool AI agent for secondhand shopping. You describe what you're looking for in plain language; FitFindr **searches** mock listings, **styles** the best find against your wardrobe, writes a **shareable caption**, and (stretch features) judges whether the **price is fair** and surfaces **live trends** in your size.

The agent orchestrates a set of tools in response to a natural-language request and handles the messy reality of what happens when a tool fails or returns nothing useful.

---

## Project layout

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # Data layer — load listings & wardrobes
├── tools.py                   # The tools (3 required + parse_query + 2 stretch)
├── agent.py                   # Planning loop (run_agent) + session state
├── app.py                     # Gradio web UI
├── planning.md                # Design doc (filled before implementation)
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Then open the localhost URL printed in your terminal (usually http://localhost:7860).

---

## Tool inventory

All tools live in `tools.py`. Inputs and return values below match the actual function signatures.

### `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`
- **Inputs:** `description` (str) — keywords to search; `size` (str | None) — optional size filter; `max_price` (float | None) — optional inclusive price ceiling.
- **Output:** `list[dict]` — matching listing dicts sorted by relevance (best first); empty list if nothing matches.
- **Purpose:** Keyword-overlap search over the dataset. Pure Python, no LLM. Filters by price/size, scores by keyword match (title & style tags weighted double), drops zero-score items, sorts.

### `suggest_outfit(new_item: dict, wardrobe: dict) -> str`
- **Inputs:** `new_item` (dict) — a single listing; `wardrobe` (dict) — `{"items": [...]}`.
- **Output:** `str` — 1–2 outfit suggestions.
- **Purpose:** LLM tool. With a non-empty wardrobe, pairs the item with named owned pieces; with an empty wardrobe, gives general styling advice. (`temperature=0.7`)

### `create_fit_card(outfit: str, new_item: dict) -> str`
- **Inputs:** `outfit` (str) — the suggestion from `suggest_outfit`; `new_item` (dict) — the listing (for name/price/platform).
- **Output:** `str` — a casual 2–4 sentence OOTD caption.
- **Purpose:** LLM tool. Writes a shareable caption mentioning the item, price, and platform once each. (`temperature=1.0` for variety)

### `parse_query(query: str) -> dict`
- **Inputs:** `query` (str) — the raw natural-language request.
- **Output:** `dict` — `{"description": str, "size": str | None, "max_price": float | None}`.
- **Purpose:** LLM tool (planning-loop helper). Extracts structured search params as JSON; falls back to `{description: query, size: None, max_price: None}` on any failure.

### `compare_price(item: dict, listings: list[dict] | None = None) -> dict` — *stretch*
- **Inputs:** `item` (dict) — the listing to evaluate; `listings` (list[dict] | None) — comparison pool, defaults to `load_listings()`.
- **Output:** `dict` — `{"verdict": str, "item_price": float | None, "median": float | None, "low": float | None, "high": float | None, "comparable_count": int}` where `verdict` is `"great deal" | "fair" | "overpriced" | "not enough data"`.
- **Purpose:** Pure Python price-fairness check. Comparables = same `category` + ≥1 shared `style_tag`. Verdict vs. median: ≤ −15% great deal, ±15% fair, > +15% overpriced.

### `get_trends(size: str | None = None, category: str | None = None, listings: list[dict] | None = None) -> dict` — *stretch*
- **Inputs:** `size` (str | None) — scopes the trend search; `category` (str | None) — optional narrowing; `listings` (list[dict] | None) — fallback pool, defaults to `load_listings()`.
- **Output:** `dict` — `{"trends": [{"style": str, "reason": str}], "sources": [{"title": str, "url": str}], "source_kind": "live" | "catalog"}`.
- **Purpose:** Live trend awareness. Uses Groq's agentic `groq/compound-mini` (built-in web search) to find current styles, then structures the findings into JSON. Falls back to dataset-derived trends if the live call fails.

> Data-layer helpers (`utils/data_loader.py`): `load_listings()`, `load_wardrobe_schema()`, `get_example_wardrobe()`, `get_empty_wardrobe()`.

---

## How the planning loop works

`run_agent(query: str, wardrobe: dict) -> dict` in `agent.py` runs a **fixed linear pipeline with one branch**. It is not a dynamic tool-picker — each step's output decides whether the next step runs:

1. **Initialize** a fresh `session` dict (`_new_session`).
2. **Parse** the query with `parse_query()` → `session["parsed"]`. If the LLM returns bad JSON, the fallback still yields a usable `description`.
3. **Trends (stretch):** call `get_trends(size=parsed["size"])` → `session["trends"]`. This depends only on the parsed size, **not** on search success, so it runs *before* search and is shown even when no items match.
4. **Search** with `search_listings(...)` → `session["search_results"]`.
   - **Branch / early exit:** if the result list is empty, set `session["error"]` to a helpful message and `return` immediately — the styling LLM tools are **never called on empty input** (saves cost and avoids nonsense). Trends from step 3 are still returned.
5. **Select** the top result (`search_results[0]`) → `session["selected_item"]`.
6. **Price check (stretch):** `compare_price(selected_item)` → `session["price_assessment"]`.
7. **Style:** `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
8. **Caption:** `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`.
9. **Return** the completed `session`.

The agent is "done" when `fit_card` is set (success) or `error` is set (early exit). The single conditional that changes behavior is the **empty-search-results check** in step 4.

---

## State management

All state lives in **one `session` dict** created by `_new_session()` — the single source of truth, passed by reference through the pipeline. Tools never hand data to each other directly; each step **reads** the fields it needs and **writes** its result back.

| Field | Written by | Read by |
|---|---|---|
| `query` | `_new_session` | parse step |
| `parsed` | `parse_query` | `search_listings`, `get_trends` |
| `trends` | `get_trends` | UI (Live trends card) |
| `search_results` | `search_listings` | selection step |
| `selected_item` | selection step | `compare_price`, `suggest_outfit`, `create_fit_card` |
| `price_assessment` | `compare_price` | UI (Price check card) |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | UI (fit-card panel) |
| `error` | any step on failure | UI (first panel) |

Because every output collects on this one object, the UI (`handle_query` in `app.py`) only needs to inspect `session` to populate all panels. `handle_query` is a **generator**: it first yields a loading state (spinners), then yields the final values once `run_agent` returns.

---

## Error-handling strategy

Every tool is built so it **never raises into the agent** — it returns a safe value, and `run_agent` decides whether to continue or stop.

| Tool | Failure mode | Response | Concrete example (from testing) |
|---|---|---|---|
| `parse_query` | LLM returns malformed / non-JSON | `try/except` → fallback `{description: query, size: None, max_price: None}` | n/a (defensive `try/except` around `json.loads`) |
| `search_listings` | No match | Returns `[]`; loop sets `session["error"]` and exits early | `"designer ballgown size XXS under $5"` → `[]` → error: *"No listings matched 'designer ballgown', size XXS, under $5. Try a broader description, a different size, or a higher price."* |
| `suggest_outfit` | Empty wardrobe | Returns general styling advice instead of erroring | Empty-wardrobe run returned a non-empty paragraph of generic advice |
| `create_fit_card` | Empty/whitespace `outfit` | Returns a descriptive error string, never raises | `create_fit_card("", {...})` → *"Couldn't create a fit card — no outfit suggestion was provided. Try generating an outfit first."* |
| `compare_price` | < 3 comparable listings | Returns `verdict: "not enough data"` | Item with a unique tag → `{"verdict": "not enough data", "comparable_count": 0}` |
| `get_trends` | Live call fails / times out / unparseable | Falls back to dataset-derived trends (`source_kind: "catalog"`) | When `groq/compound` returned **HTTP 413** (and `compound-mini` hit a **429** rate limit), `get_trends` returned catalog trends like `vintage, cottagecore, earth tones, …` |

---

## Spec reflection

**One way the spec helped:** Writing each tool's contract in `planning.md` first — inputs, return type, and *failure mode* — made the implementation and the loop fall out cleanly. Documenting up front that `search_listings` *"returns an empty list if nothing matches — does NOT raise"* is exactly what made the **empty-results early-exit branch** in the planning loop obvious: the loop only has to check `if not search_results`, and no tool needs try/except for "no match."

**One way implementation diverged:** The spec/docstring described size matching as case-insensitive **substring** matching (*"M" matches "S/M"*). When implemented that way, testing `search_listings('boots', size='8')` showed substring matching was too loose — `"8"` also matched `"W28"` and `"US 8.5"`. The implementation diverged to **token-based** matching (`_size_matches` splits the size on spaces/slashes and matches whole tokens), so `"8"` matches `"US 8"` but **not** `"W28"` or `"US 8.5"`, while still honoring the documented `"M"` → `"S/M"` case. The divergence was driven by a real false-positive found in testing, not a change of intent.

---

## AI usage

This project was built with AI assistance (Claude). Two specific instances:

**1. Implementing `search_listings`, then overriding the size logic.**
I directed the AI to implement `search_listings` from my `planning.md` Tool 1 spec (keyword-overlap scoring, price/size filters, return `[]` on no match) and to test it on three queries. The AI's first version used substring size matching per the docstring. Testing surfaced false positives (`size="8"` matched `"W28"`/`"US 8.5"`), so I had it **override** that with token-based matching (`_size_matches`) and re-verified with unit checks (`"m"`→`"S/M"` ✓, `"8"`→`"US 8"` ✓, `"8"`✗`"W28"`).

**2. Choosing the trend-tool data source.**
I directed the AI to build the stretch `get_trends` tool using a *real external* live source. The AI probed candidates and reported back: Depop and Reddit return `403` (bot-blocked), and Groq's `groq/compound` returned `413` (request too large) on this account. Based on that evidence I had it **switch** to `groq/compound-mini` (which performed real web search and returned dated source URLs) and add an automatic **dataset fallback** so the feature degrades gracefully under rate limits instead of breaking. I also overrode the original "no-auth scrape" idea once the 403s proved it wasn't viable.


