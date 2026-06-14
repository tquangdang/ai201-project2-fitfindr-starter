# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
search_listings will receive an item, its size and max price from the user's prompt, then use those to find a list of suitable items in the database

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): the item user is looking for
- `size` (str): item's size
- `max_price` (float): max price of the item

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A list of matching listing dicts, sorted by relevance (best match first).


**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
Returns an empty list if nothing matches 
---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Given a thrifted item and user's wardrobe, suggest 1 - 2 complete outfits
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A single thrifted listing dict (the top search result the user is considering)
- `wardrobe` (dict): The user's wardrobe — a dict with an `items` list

**What it returns:**
<!-- Describe the return value -->
A non-empty string with outfit suggestion
**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
Offer general styling advice for the item, rather than raising an exception or returning an empty string.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Generate a short, shareable outfit caption for the thrifted find
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The outfit suggestion string from suggest_outfit()
- `new_item` (dict): The thrifted listing dict — supplies the item name, price, and platform for the caption

**What it returns:**
<!-- Describe the return value -->
A 2–4 sentence string usable as an Instagram/TikTok caption.
**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
return a descriptive error message string 
---

### Additional Tools (if any)

#### Tool 4: compare_price (stretch — price fairness)

**What it does:**
Given a listing, finds comparable items already in the dataset and judges whether the item's price is a great deal, fair, or overpriced. Pure Python, no LLM.

**Input parameters:**
- `item` (dict): the selected listing being evaluated.
- `listings` (list[dict], optional): the pool to compare against; defaults to `load_listings()`.

**What it returns:**
A dict: `{ "verdict": "great deal" | "fair" | "overpriced" | "not enough data", "item_price": float, "median": float, "low": float, "high": float, "comparable_count": int }`.
- Comparable = same `category` AND sharing ≥1 `style_tag` (size-agnostic); the item itself is excluded.
- Verdict vs. median of comparables: `≤ −15%` → great deal, within `±15%` → fair, `> +15%` → overpriced.

**What happens if it fails or returns nothing:**
If fewer than 3 comparables are found, return `verdict: "not enough data"` rather than making a weak claim. Never raises.

---

#### Tool 5: get_trends (stretch — live trend awareness)

**What it does:**
Surfaces fashion styles currently trending for the user's size range, using **live web search** via Groq's agentic `groq/compound` model (it searches the web server-side, so no scraping/API key and no bot-blocking).

**Input parameters:**
- `size` (str | None): the parsed size, used to scope the trend query.
- `category` (str | None, optional): narrows trends to a clothing category when known.

**What it returns:**
A dict: `{ "trends": [ {"style": str, "reason": str}, ... ], "sources": [ {"title": str, "url": str}, ... ] }`.
Sources come from the model's `executed_tools` search results and are shown as citations so the user can see it is real/live.

**What happens if it fails or returns nothing:**
If the live call fails, times out, or returns unparseable output, fall back to **dataset-derived trends** — the most common `style_tags` among listings in the user's size — so the panel always shows something. Never raises.

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The agent follows a fixed linear pipeline, not a dynamic tool-picking loop. Each step's output decides whether the next step runs.
1. Parse the query into description, size, max_price by asking the LLM to return structured JSON, then store the parsed dict in session["parsed"]. If the LLM returns malformed JSON, fall back to using the raw query as the description with size/max_price set to None.
2. (Stretch) Call get_trends(size) → trends. This depends only on the parsed size, not on search success, so it runs early and is shown even on the no-results path.
3. Call search_listings(). Branch point: if it returns an empty list, set session["error"] and stop — don't call the styling LLM tools on empty input (trends from step 2 are still returned).
4. Otherwise select the top result (search_results[0]) as selected_item.
5. (Stretch) Call compare_price(selected_item) → price_assessment.
6. Call suggest_outfit(selected_item, wardrobe) → outfit_suggestion.
7. Call create_fit_card(outfit_suggestion, selected_item) → fit_card.
The agent is "done" when fit_card is set (success) or error is set (early exit). The stretch outputs (trends, price_assessment) feed a combined "Insights" panel in the UI, separate from the original three panels.
---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
All state lives in one `session` dict created by `_new_session()` in agent.py. It is the single source of truth and is passed by reference through the pipeline. Each step reads the fields it needs and writes its result back, so tools never pass data to each other directly — everything funnels through `session`.

| Field | Written by | Read by |
|---|---|---|
| `query` | `_new_session` | parse step |
| `parsed` | parse step | `search_listings` |
| `search_results` | `search_listings` | selection step |
| `selected_item` | selection step | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `trends` | `get_trends` (stretch) | UI Insights panel |
| `price_assessment` | `compare_price` (stretch) | UI Insights panel |
| `error` | any step on failure | UI (app.py) |

Because all output is collected on this one object, the UI only needs to inspect `session` to render its panels.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| parse query (LLM) | LLM returns malformed or non-JSON output | Falls back to using the raw query as `description` with `size` and `max_price` set to None, so search can still run instead of crashing. |
| search_listings | No results match the query | Returns `[]`. The loop sets `session["error"]` to a helpful message (e.g. "No listings matched 'X' — try a broader description or higher price") and returns early, skipping `suggest_outfit` and `create_fit_card`. |
| suggest_outfit | Wardrobe is empty (`items == []`) | Does not error. Calls the LLM for general styling advice for the item instead of wardrobe-specific combinations, and still returns a non-empty string. |
| create_fit_card | Outfit input is missing or incomplete | Guards against an empty/whitespace-only `outfit`; returns a descriptive error-message string (never an exception or empty string) so the UI can still display something. |
| compare_price (stretch) | Fewer than 3 comparable listings | Returns `verdict: "not enough data"` instead of a misleading judgment; never raises. |
| get_trends (stretch) | Live web-search call fails, times out, or returns unparseable output | Falls back to dataset-derived trends (most common `style_tags` in the user's size); never raises and the panel always shows something. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
                ┌─────────────────────────────────────┐
  user query ─► │            run_agent()              │
                │           (planning loop)           │
                │                                     │
                │   parse query ──► session["parsed"] │
                └───────────────┬─────────────────────┘
                                ▼
                       search_listings()
                                │
                  empty? ──Yes──► set session["error"] ──► RETURN early
                                │No
                                ▼
                     selected_item = search_results[0]
                                │
                                ▼
                  suggest_outfit(item, wardrobe) ──► outfit_suggestion
                                │
                                ▼
                  create_fit_card(outfit, item) ──► fit_card
                                │
                                ▼
                        return session ──► app.py (3 output panels)

   The session dict threads through every step (each step reads + writes it).
   The only branch is the empty-results early exit after search_listings.
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude for all three tools, feeding it one Tool spec from this doc at a time plus the relevant context.
- `search_listings`: I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and the field list returned by `load_listings()`, and ask it to implement keyword-overlap scoring with optional price and size filters (no LLM call — pure Python). I'll verify with three queries: a clear match, a price-filtered match, and a deliberate no-match — confirming the last returns `[]` rather than raising.
- `suggest_outfit`: I'll give Claude the Tool 2 spec plus the `_get_groq_client()` helper and the wardrobe `items` shape, and ask it to build the prompt and call the LLM. I'll verify both branches: a normal wardrobe (names real wardrobe pieces) and the empty wardrobe (returns general styling advice, never an empty string).
- `create_fit_card`: I'll give Claude the Tool 3 spec and ask for a higher-temperature caption that mentions item name, price, and platform once each. I'll verify the empty-`outfit` guard returns an error string, and that two different inputs produce different captions.
- LLM query parser: I'll ask Claude for a function that prompts the LLM to return `{description, size, max_price}` as JSON, parses it, and falls back to `{description: raw_query, size: None, max_price: None}` on a JSON error. I'll verify it on the five example queries — e.g. `$30` → `max_price=30.0`, "size M" → `size="M"`.

**Milestone 4 — Planning loop and state management:**
I'll give Claude my Planning Loop and State Management sections plus the `session` dict shape from `_new_session()`, and ask it to implement `run_agent()` following the numbered steps, including the empty-results early exit. I'll verify with the two `__main__` test cases already in agent.py (happy path + no-results path), checking that `session["error"]` is None on success and set on the no-results query, before wiring `handle_query()` in app.py.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
`run_agent()` initializes the session and sends the query to the LLM parser. The LLM returns `{description: "vintage graphic tee", size: None, max_price: 30.0}` (the mention of baggy jeans / chunky sneakers is wardrobe context, not a search filter), stored in `session["parsed"]`. If the LLM had returned bad JSON, it would fall back to using the whole query as the description.

**Step 2:**
The agent calls `search_listings("vintage graphic tee", None, 30.0)`. It loads all 40 listings, drops anything over $30, scores the rest by keyword overlap with the description, drops zero-score items, and returns the ranked list into `session["search_results"]`. The list is non-empty, so the agent selects `search_results[0]` as `session["selected_item"]` and continues. (If it had been empty, the agent would set `session["error"]` and return here.)

**Step 3:**
The agent calls `suggest_outfit(selected_item, wardrobe)`. The wardrobe is non-empty, so the LLM is prompted with the tee plus the wardrobe items and returns 1–2 outfit ideas pairing the tee with the baggy jeans and chunky sneakers. The result is stored in `session["outfit_suggestion"]`.

**Step 4:**
The agent calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM writes a casual 2–4 sentence caption naming the tee, its price, and its platform once each. The result is stored in `session["fit_card"]`, and the agent returns the session.

**Final output to user:**
The Gradio UI reads the session and fills its three panels: the top listing's details, the outfit idea, and the shareable fit card. If `session["error"]` had been set, the UI would instead show that message in the first panel and leave the other two blank.
