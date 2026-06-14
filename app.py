"""
app.py

Gradio interface for FitFindr. handle_query() calls run_agent() and maps the
session results to the three output panels, streaming a loading state first so
the UI feels responsive while the agent's LLM calls run.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import html

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── panel content helpers ─────────────────────────────────────────────────────

def _esc(value) -> str:
    """HTML-escape a value for safe interpolation into the listing card."""
    return html.escape(str(value)) if value is not None else ""


def _listing_card_html(item: dict) -> str:
    """Render the selected listing as a styled HTML card."""
    price = item.get("price")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "—"
    condition = (item.get("condition") or "").lower()

    chips = "".join(
        f'<span class="ff-chip">{_esc(tag)}</span>'
        for tag in item.get("style_tags", [])[:6]
    )
    colors = " · ".join(item.get("colors", []))
    colors_html = f'<div class="ff-colors">🎨 {_esc(colors)}</div>' if colors else ""

    return f"""
<div class="ff-listing">
  <div class="ff-listing-top">
    <h3 class="ff-listing-title">{_esc(item.get('title', 'Untitled'))}</h3>
    <span class="ff-price">{price_str}</span>
  </div>
  <p class="ff-desc">{_esc(item.get('description', ''))}</p>
  <div class="ff-chips">{chips}</div>
  <div class="ff-meta">
    <span class="ff-badge ff-cond-{_esc(condition)}">{_esc((item.get('condition') or '—').title())}</span>
    <span class="ff-pill">📂 {_esc(item.get('category', '—'))}</span>
    <span class="ff-pill">📏 {_esc(item.get('size', '—'))}</span>
    <span class="ff-pill">🔖 {_esc(item.get('brand') or 'Unbranded')}</span>
    <span class="ff-pill ff-platform">🛒 {_esc(item.get('platform', '—'))}</span>
  </div>
  {colors_html}
</div>
"""


# Empty + loading states carry inline styles so they render identically whether
# shown in a gr.HTML panel or embedded inside a gr.Markdown panel.
_STATE_WRAP = (
    "display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "gap:0.6rem;min-height:200px;height:100%;text-align:center;color:#9db5c8;"
)


def _empty_html(icon: str, message: str) -> str:
    return (
        f'<div class="ff-empty" style="{_STATE_WRAP}">'
        f'<div style="font-size:1.9rem;opacity:0.75;">{icon}</div>'
        f'<p style="margin:0;font-size:0.86rem;max-width:240px;">{_esc(message)}</p></div>'
    )


def _loading_html(message: str) -> str:
    return (
        f'<div class="ff-loading" style="{_STATE_WRAP}">'
        '<div class="ff-spin" style="width:34px;height:34px;border-radius:50%;'
        'border:3px solid #2c4257;border-top-color:#8fccea;"></div>'
        f'<p style="margin:0;font-size:0.86rem;">{_esc(message)}</p></div>'
    )


LISTING_EMPTY = _empty_html("🔎", "Describe a piece and your find will appear here.")
OUTFIT_EMPTY = _empty_html("👗", "Your outfit ideas will appear here.")
FITCARD_EMPTY = _empty_html("✨", "Your shareable caption will appear here.")
LISTING_LOADING = _loading_html("Searching secondhand listings…")
OUTFIT_LOADING = _loading_html("Styling it with your wardrobe…")
FITCARD_LOADING = _loading_html("Writing your caption…")


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str):
    """
    Called by Gradio when the user submits a query. Implemented as a generator
    so the UI shows a loading state immediately, then the results once the agent
    finishes.

    Yields a tuple of three values, one per output panel:
        (listing_html, outfit_markdown, fit_card_markdown)
    """
    # 1. Guard against an empty query.
    if not user_query or not user_query.strip():
        yield (
            _empty_html("✏️", 'Tell me what you\'re after — try "vintage graphic tee under $30, size M".'),
            OUTFIT_EMPTY,
            FITCARD_EMPTY,
        )
        return

    # 2. Immediate loading state while the agent works.
    yield LISTING_LOADING, OUTFIT_LOADING, FITCARD_LOADING

    # 3. Select the wardrobe and run the agent.
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    session = run_agent(user_query.strip(), wardrobe)

    # 4. Error path — show the message in the first panel.
    if session["error"]:
        yield _empty_html("🛒", session["error"]), OUTFIT_EMPTY, FITCARD_EMPTY
        return

    # 5. Success path — rich listing card + outfit + fit card.
    yield (
        _listing_card_html(session["selected_item"]),
        session["outfit_suggestion"],
        session["fit_card"],
    )


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap');

.gradio-container {
    background:
        radial-gradient(1100px 520px at 50% -8%, rgba(143,204,234,0.12), transparent 60%),
        linear-gradient(180deg, #142536 0%, #0f1c2a 100%) !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 3rem 2rem !important;
    --ff-accent: #8fccea;
    --ff-accent-strong: #6fb6dc;
    --ff-surface: #1a2a3a;
    --ff-surface-2: #213446;
    --ff-border: #2c4257;
    --ff-text: #eaf3fa;
    --ff-muted: #9db5c8;

    /* Harmonize Gradio's own components with the theme */
    --block-label-background-fill: var(--ff-surface-2) !important;
    --block-label-text-color: var(--ff-muted) !important;
    --block-label-border-color: var(--ff-border) !important;
    --block-title-text-color: var(--ff-muted) !important;
    --border-color-primary: var(--ff-border) !important;
    --table-border-color: var(--ff-border) !important;
    --table-even-background-fill: var(--ff-surface) !important;
    --table-odd-background-fill: #16273a !important;

    /* Tone the selected radio down to a subtle accent-bordered chip */
    --checkbox-label-background-fill-selected: var(--ff-surface-2) !important;
    --checkbox-label-text-color-selected: var(--ff-text) !important;
    --checkbox-background-color-selected: var(--ff-accent) !important;
    --checkbox-border-color-selected: var(--ff-accent) !important;
}

/* Hide Gradio's default footer for a cleaner branded look */
footer { display: none !important; }

/* Input labels: subtle chip instead of a bright primary pill */
.ff-controls .block-label, .ff-controls span[data-testid="block-info"] {
    background: var(--ff-surface-2) !important;
    color: var(--ff-muted) !important;
    border: 1px solid var(--ff-border) !important;
    font-weight: 600 !important;
}

/* ── Hero ────────────────────────────────────────────────── */
#ff-hero { text-align: center; padding: 2.8rem 1rem 0.4rem; position: relative; }
#ff-hero::before {
    content: ""; position: absolute; top: -30px; left: 50%; transform: translateX(-50%);
    width: 440px; height: 220px; pointer-events: none; z-index: 0;
    background: radial-gradient(closest-side, rgba(143,204,234,0.20), transparent);
    filter: blur(14px);
}
#ff-hero > * { position: relative; z-index: 1; }
#ff-hero .ff-logo {
    font-family: 'Fraunces', serif;
    font-size: 3.3rem; font-weight: 700; letter-spacing: -0.02em;
    color: var(--ff-text); line-height: 1;
}
#ff-hero .ff-logo .accent { color: var(--ff-accent); text-shadow: 0 0 26px rgba(143,204,234,0.45); }
#ff-hero .ff-kicker {
    text-transform: uppercase; letter-spacing: 0.3em; font-size: 0.72rem;
    color: var(--ff-accent); font-weight: 600; margin-bottom: 0.7rem;
}
#ff-hero .ff-tagline {
    font-size: 1.04rem; color: var(--ff-muted); max-width: 640px;
    margin: 0.8rem auto 0; line-height: 1.55;
}
.ff-badges { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-top: 1.1rem; }
.ff-badges span {
    background: var(--ff-surface); border: 1px solid var(--ff-border); color: var(--ff-muted);
    padding: 0.26rem 0.72rem; border-radius: 999px; font-size: 0.76rem;
}

/* ── Step strip ──────────────────────────────────────────── */
.ff-steps {
    display: flex; gap: 0.7rem; justify-content: center;
    margin: 1.6rem auto 0.4rem; max-width: 900px; flex-wrap: wrap;
}
.ff-step {
    flex: 1 1 220px; display: flex; gap: 0.7rem; align-items: flex-start;
    background: var(--ff-surface); border: 1px solid var(--ff-border);
    border-radius: 12px; padding: 0.9rem 1.05rem; text-align: left;
    transition: transform 0.16s ease, border-color 0.16s ease;
}
.ff-step:hover { transform: translateY(-2px); border-color: var(--ff-accent); }
.ff-step .ff-num {
    font-family: 'Fraunces', serif; font-size: 1.15rem; font-weight: 600;
    color: var(--ff-accent); line-height: 1.4;
}
.ff-step b { color: var(--ff-text); font-size: 0.92rem; }
.ff-step p { color: var(--ff-muted); font-size: 0.8rem; margin: 0.15rem 0 0; line-height: 1.4; }

/* ── Controls ────────────────────────────────────────────── */
.ff-controls {
    background: var(--ff-surface) !important; border: 1px solid var(--ff-border) !important;
    border-radius: 16px !important; padding: 1.1rem 1.3rem !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.ff-controls textarea:focus, .ff-controls input:focus {
    border-color: var(--ff-accent) !important;
    box-shadow: 0 0 0 3px rgba(143,204,234,0.16) !important;
}

/* ── Find button ─────────────────────────────────────────── */
#ff-find {
    display: block !important; margin: 0.5rem auto 0 !important;
    max-width: 460px !important; width: 100% !important;
    background: linear-gradient(180deg, #7cc0e3 0%, #4f9bc6 100%) !important;
    color: #08263a !important;
    border: none !important; font-weight: 600 !important; font-size: 0.98rem !important;
    border-radius: 11px !important; letter-spacing: 0.01em;
    padding: 0.62rem 1.2rem !important; min-height: 0 !important;
    box-shadow: 0 6px 20px rgba(124,192,227,0.22);
    transition: filter 0.15s ease, transform 0.1s ease, box-shadow 0.15s ease;
}
#ff-find:hover { filter: brightness(1.05); transform: translateY(-1px); box-shadow: 0 9px 26px rgba(124,192,227,0.3); }
#ff-find:active { transform: translateY(0); }

/* ── Output cards ────────────────────────────────────────── */
.ff-results { gap: 1rem !important; }
.ff-card {
    background: var(--ff-surface) !important; border: 1px solid var(--ff-border) !important;
    border-radius: 14px !important; padding: 0 !important; overflow: hidden;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.ff-card:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(0,0,0,0.34); border-color: var(--ff-accent) !important; }
.ff-card-title h3 {
    margin: 0 !important; padding: 0.82rem 1.1rem !important;
    font-size: 0.9rem !important; font-weight: 600 !important; color: var(--ff-text) !important;
    background: var(--ff-surface-2); border-bottom: 1px solid var(--ff-border);
}
.ff-card-body { padding: 0.7rem 1.1rem 1.1rem !important; min-height: 210px; display: flex; flex-direction: column; }
.ff-card-body > * { width: 100%; }
.ff-card-body, .ff-card-body p, .ff-card-body li { font-size: 0.9rem; line-height: 1.58; color: var(--ff-text); }
.ff-card-body strong { color: var(--ff-text); }
.ff-caption p { font-style: italic; font-size: 0.95rem; line-height: 1.62; }

/* Reveal animation for result text (listing card animates on its own) */
.ff-card-body p, .ff-card-body h3, .ff-card-body ul, .ff-card-body table { animation: ff-fade 0.4s ease; }

/* ── Copy caption button ─────────────────────────────────── */
#ff-copy {
    align-self: flex-start; width: auto !important; flex: none !important;
    margin: 0 1.1rem 1.1rem 1.1rem !important; min-width: 0 !important; min-height: 0 !important;
    background: var(--ff-surface-2) !important; color: var(--ff-accent) !important;
    border: 1px solid var(--ff-border) !important; border-radius: 8px !important;
    font-size: 0.8rem !important; font-weight: 600 !important; padding: 0.36rem 0.78rem !important;
    box-shadow: none !important; transition: background 0.15s ease, border-color 0.15s ease;
}
#ff-copy:hover { border-color: var(--ff-accent) !important; background: rgba(143,204,234,0.12) !important; }

/* empty + loading states */
.ff-empty, .ff-loading {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.6rem; min-height: 200px; height: 100%; flex: 1; text-align: center; color: var(--ff-muted);
}
.ff-empty-ico { font-size: 1.9rem; opacity: 0.75; }
.ff-empty p, .ff-loading p { margin: 0; font-size: 0.86rem; max-width: 240px; }
.ff-spin {
    width: 34px; height: 34px; border-radius: 50%;
    border: 3px solid var(--ff-border); border-top-color: var(--ff-accent);
    animation: ff-rot 0.8s linear infinite;
}
@keyframes ff-rot { to { transform: rotate(360deg); } }

/* listing card */
.ff-listing { animation: ff-fade 0.35s ease; }
@keyframes ff-fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.ff-listing-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.6rem; }
.ff-listing-title { font-family: 'Fraunces', serif; font-size: 1.22rem; line-height: 1.25; margin: 0.15rem 0 0; color: var(--ff-text); }
.ff-price {
    background: var(--ff-accent); color: #0f2030; font-weight: 700;
    padding: 0.22rem 0.62rem; border-radius: 8px; font-size: 1.02rem; white-space: nowrap;
}
.ff-desc { color: var(--ff-muted); font-size: 0.88rem; line-height: 1.5; margin: 0.75rem 0 0; }
.ff-chips { display: flex; flex-wrap: wrap; gap: 0.36rem; margin: 0.7rem 0 0; }
.ff-chip {
    background: rgba(143,204,234,0.12); color: var(--ff-accent);
    border: 1px solid rgba(143,204,234,0.26); padding: 0.13rem 0.56rem;
    border-radius: 999px; font-size: 0.72rem; letter-spacing: 0.02em;
}
.ff-meta { display: flex; flex-wrap: wrap; gap: 0.42rem; margin-top: 0.85rem; }
.ff-pill {
    background: rgba(255,255,255,0.05); border: 1px solid var(--ff-border); color: var(--ff-text);
    padding: 0.2rem 0.56rem; border-radius: 8px; font-size: 0.76rem;
}
.ff-badge { padding: 0.2rem 0.56rem; border-radius: 8px; font-size: 0.76rem; font-weight: 600; }
.ff-cond-excellent { background: rgba(111,207,151,0.16); color: #7ddca0; border: 1px solid rgba(111,207,151,0.32); }
.ff-cond-good { background: rgba(143,204,234,0.16); color: var(--ff-accent); border: 1px solid rgba(143,204,234,0.32); }
.ff-cond-fair { background: rgba(224,176,74,0.16); color: #e6bd60; border: 1px solid rgba(224,176,74,0.32); }
.ff-colors { margin-top: 0.75rem; color: var(--ff-muted); font-size: 0.78rem; }

/* ── Examples table ──────────────────────────────────────── */
.ff-examples {
    background: var(--ff-surface) !important; border: 1px solid var(--ff-border) !important;
    border-radius: 16px !important; padding: 0.9rem 1.1rem 1.1rem !important; margin-top: 0.5rem;
}
.ff-examples table { border-collapse: separate !important; border-spacing: 0; overflow: hidden; border-radius: 10px; }
.ff-examples thead th {
    background: var(--ff-surface-2) !important; color: var(--ff-text) !important;
    font-weight: 600 !important; border-bottom: 1px solid var(--ff-border) !important;
}
.ff-examples td, .ff-examples th { border-color: var(--ff-border) !important; }
.ff-examples tbody tr { cursor: pointer; transition: background 0.12s ease; }
.ff-examples tbody tr:hover td { background: rgba(143,204,234,0.10) !important; color: var(--ff-text) !important; }

/* footer */
.ff-foot {
    text-align: center; color: var(--ff-muted); font-size: 0.78rem;
    padding: 1.6rem 0 0.6rem; margin-top: 0.4rem; border-top: 1px solid var(--ff-border);
}

/* ── Responsive ──────────────────────────────────────────── */
@media (max-width: 1000px) {
    .gradio-container { padding: 0 1rem 2rem !important; }
    .ff-results { flex-direction: column !important; }
    #ff-hero .ff-logo { font-size: 2.5rem; }
}
"""

HERO_HTML = """
<div id="ff-hero">
  <div class="ff-kicker">Secondhand, styled</div>
  <div class="ff-logo">Fit<span class="accent">Findr</span></div>
  <p class="ff-tagline">
    Thrifting is a whole process — searching across platforms, picturing the fit
    with what you already own, and deciding if it's worth it. FitFindr does the
    searching, styling, and reasoning for you.
  </p>
  <div class="ff-badges">
    <span>🧺 40+ curated listings</span>
    <span>🛒 Depop · ThredUp · Poshmark</span>
    <span>🤖 AI-styled outfits</span>
  </div>
</div>
<div class="ff-steps">
  <div class="ff-step"><span class="ff-num">01</span>
    <div><b>Search</b><p>Scan secondhand listings for the piece you described.</p></div></div>
  <div class="ff-step"><span class="ff-num">02</span>
    <div><b>Style</b><p>Pair it against your wardrobe for outfits that work.</p></div></div>
  <div class="ff-step"><span class="ff-num">03</span>
    <div><b>Share</b><p>Get a ready-to-post caption for your new find.</p></div></div>
</div>
"""


# Client-side copy: read the rendered caption text and write it to the clipboard,
# with a brief "Copied!" confirmation. No-ops while a placeholder/loader is shown.
COPY_JS = """
() => {
    const card = document.querySelector('#ff-fitcard');
    if (!card || card.querySelector('.ff-empty, .ff-loading')) return;
    const text = card.innerText.trim();
    if (!text) return;
    navigator.clipboard.writeText(text);
    const btn = document.querySelector('#ff-copy');
    if (btn) {
        const original = btn.dataset.label || btn.innerText;
        btn.dataset.label = original;
        btn.innerText = '✓ Copied!';
        setTimeout(() => { btn.innerText = original; }, 1500);
    }
}
"""


THEME = gr.themes.Soft(
    primary_hue="sky",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
)


def build_interface():
    with gr.Blocks(title="FitFindr — Secondhand, styled") as demo:
        gr.HTML(HERO_HTML)

        with gr.Row(elem_classes="ff-controls"):
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Style against",
                scale=1,
            )

        submit_btn = gr.Button("✨  Find my fit", variant="primary", elem_id="ff-find")

        with gr.Row(equal_height=True, elem_classes="ff-results"):
            with gr.Column(elem_classes="ff-card"):
                gr.Markdown("### 🛍️ The find", elem_classes="ff-card-title")
                listing_output = gr.HTML(LISTING_EMPTY, elem_classes="ff-card-body")
            with gr.Column(elem_classes="ff-card"):
                gr.Markdown("### 👗 How to wear it", elem_classes="ff-card-title")
                outfit_output = gr.Markdown(OUTFIT_EMPTY, elem_classes="ff-card-body")
            with gr.Column(elem_classes="ff-card"):
                gr.Markdown("### ✨ Your fit card", elem_classes="ff-card-title")
                fitcard_output = gr.Markdown(
                    FITCARD_EMPTY, elem_id="ff-fitcard", elem_classes=["ff-card-body", "ff-caption"]
                )
                copy_btn = gr.Button("📋 Copy caption", elem_id="ff-copy")

        with gr.Column(elem_classes="ff-examples"):
            gr.Examples(
                examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
                inputs=[query_input, wardrobe_choice],
                label="Try one of these",
            )

        gr.HTML(
            '<div class="ff-foot">FitFindr · a multi-tool AI styling agent · '
            "searches → styles → shares</div>"
        )

        outputs = [listing_output, outfit_output, fitcard_output]
        submit_btn.click(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)
        query_input.submit(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)
        copy_btn.click(fn=None, inputs=None, outputs=None, js=COPY_JS)

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch(theme=THEME, css=CUSTOM_CSS)
