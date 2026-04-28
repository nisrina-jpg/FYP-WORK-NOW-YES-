import asyncio
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

app = FastAPI(
    title="Zakat Selangor Scraper API",
    description="Scrapes zakat calculator fields from zakatselangor.com.my",
    version="1.0.0",
)

TARGET_URL = "https://www.zakatselangor.com.my/kira-zakat/"
CACHE_FILE = "zakat_data_selangor.json"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your domain in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# JS: scrape only VISIBLE h3 sections and their VISIBLE inputs
# ---------------------------------------------------------------------------

SCRAPE_VISIBLE_JS = """
() => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
        let parent = el.parentElement;
        while (parent && parent !== document.body) {
            const ps = getComputedStyle(parent);
            if (ps.display === 'none' || ps.visibility === 'hidden') return false;
            parent = parent.parentElement;
        }
        return true;
    }

    function getLabelForInput(inp) {
        if (inp.id) {
            const lbl = document.querySelector('label[for="' + inp.id + '"]');
            if (lbl && isVisible(lbl)) return lbl.innerText.trim();
        }
        const wrap = inp.closest('label');
        if (wrap) {
            return wrap.innerText.replace(/[\\d.,]+/g, '').trim();
        }
        let curr = inp;
        for (let i = 0; i < 5; i++) {
            let p = curr.parentElement;
            if (!p) break;
            for (let child of p.children) {
                if (child === curr || child.contains(inp)) continue;
                let t = child.innerText ? child.innerText.trim() : '';
                if (t && t !== 'RM' && t !== '00.00' && t !== '0.00' && t !== '0' && t.length > 2) {
                    return t.replace(/\\s+/g, ' ').trim();
                }
            }
            curr = p;
        }
        let fallback = inp.getAttribute('aria-label') || inp.placeholder || '';
        if (fallback === '00.00' || fallback === '0.00' || fallback === '0') fallback = '';
        return fallback;
    }

    const result = {};
    const seen_sections = new Set();
    const allH3 = Array.from(document.querySelectorAll('h3'));
    const visibleH3 = allH3.filter(isVisible);

    for (const h3 of visibleH3) {
        const heading = h3.innerText.trim();
        if (!heading || seen_sections.has(heading)) continue;
        seen_sections.add(heading);

        const fields = [];
        const seen_labels = new Set();

        let el = h3.nextElementSibling;
        while (el && el.tagName !== 'H3') {
            if (isVisible(el)) {
                const inputs = el.querySelectorAll(
                    'input[type="number"], input[type="text"], input:not([type]), select'
                );
                for (const inp of inputs) {
                    if (!isVisible(inp)) continue;
                    let label = getLabelForInput(inp);
                    if (!label && inp.id) label = "ID: " + inp.id;
                    if (!label || seen_labels.has(label)) continue;
                    seen_labels.add(label);
                    fields.push({
                        label:       label,
                        input_id:    inp.id    || '',
                        input_name:  inp.name  || '',
                        input_type:  inp.type  || 'text',
                        input_value: inp.value || '',
                    });
                }
            }
            el = el.nextElementSibling;
        }

        if (fields.length > 0) {
            result[heading] = fields;
        }
    }

    return result;
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def open_dropdown_and_pick(page, item_text: str):
    current_text = "Zakat Pendapatan" if item_text == "Zakat Perniagaan" else "Zakat Perniagaan"
    opened = False
    triggers = [
        f"text=\"{current_text}\"",
        "[role='combobox']",
        ".vs__dropdown-toggle",
        "[class*='dropdown-toggle']",
    ]
    for sel in triggers:
        try:
            elements = await page.locator(sel).all()
            for el in reversed(elements):
                if await el.is_visible():
                    await el.click(timeout=1500)
                    await page.wait_for_timeout(800)
                    opened = True
                    break
            if opened:
                break
        except Exception:
            continue

    clicked = False
    options = [
        f"[role='option']:has-text('{item_text}')",
        f"li:has-text('{item_text}')",
        f".dropdown-item:has-text('{item_text}')",
        f"text=\"{item_text}\"",
    ]
    for sel in options:
        try:
            elements = await page.locator(sel).all()
            for el in reversed(elements):
                if await el.is_visible():
                    await el.click(timeout=1500)
                    await page.wait_for_timeout(2000)
                    clicked = True
                    break
            if clicked:
                break
        except Exception:
            continue

    return clicked


async def click_subtab(page, text: str):
    for sel in [
        f"label:has-text('{text}')",
        f"[type='radio'] + label:has-text('{text}')",
        f"button:has-text('{text}')",
        f"[role='tab']:has-text('{text}')",
        f"text={text}",
    ]:
        try:
            await page.locator(sel).first.click(timeout=2000)
            await page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    return False


async def scrape_visible(page) -> dict:
    return await page.evaluate(SCRAPE_VISIBLE_JS)


# ---------------------------------------------------------------------------
# Core scrape logic
# ---------------------------------------------------------------------------

async def scrape_zakat_calculator() -> dict:
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2500)

        # 1. Zakat Pendapatan — Tanpa Tolakan
        await open_dropdown_and_pick(page, "Zakat Pendapatan")
        await click_subtab(page, "Tanpa Tolakan")
        results["zakat_pendapatan_tanpa_tolakan"] = await scrape_visible(page)

        # 2. Zakat Pendapatan — Dengan Tolakan
        await click_subtab(page, "Dengan Tolakan")
        results["zakat_pendapatan_dengan_tolakan"] = await scrape_visible(page)

        # 3. Zakat Perniagaan
        await open_dropdown_and_pick(page, "Zakat Perniagaan")
        results["zakat_perniagaan"] = await scrape_visible(page)

        await browser.close()

    return results


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
def root():
    return {"status": "ok", "message": "Zakat Selangor Scraper API is running"}


@app.get("/scrape", summary="Live scrape (no cache)")
async def scrape():
    """Scrapes the Zakat Selangor calculator live. Takes ~15–30s."""
    try:
        return await scrape_zakat_calculator()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scrape-cached", summary="Return cached data, or scrape if no cache exists")
async def scrape_cached():
    """Returns cached JSON if available, otherwise runs a live scrape and caches it."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    data = await scrape_zakat_calculator()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


@app.get("/refresh", summary="Force re-scrape and update cache")
async def refresh():
    """Forces a fresh scrape and overwrites the cache file."""
    try:
        data = await scrape_zakat_calculator()
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "refreshed", "sections": list(data.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
