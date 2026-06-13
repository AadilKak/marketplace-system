import asyncio
import os
from playwright.async_api import async_playwright

# Burner account credentials — set these as environment variables on Render
FB_EMAIL = os.environ.get("FB_EMAIL", "")
FB_PASSWORD = os.environ.get("FB_PASSWORD", "")

# Path to store the saved login session so we don't re-login every time
SESSION_FILE = "fb_session.json"


def _ensure_session_file():
    """
    Write fb_session.json from the FB_SESSION env var if the file doesn't exist locally.
    This lets Render (ephemeral filesystem) reconstruct the session on each boot.
    """
    import base64
    env_session = os.environ.get("FB_SESSION", "")
    if env_session and not os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "wb") as f:
            f.write(base64.b64decode(env_session))
        print("Session file restored from FB_SESSION env var.")

    if not os.path.exists(SESSION_FILE):
        raise RuntimeError(
            f"No session file found at '{SESSION_FILE}' and FB_SESSION env var is not set.\n"
            "Locally: run `python save_session.py`.\n"
            "On Render: run `python export_session.py` locally and set FB_SESSION in Render env vars."
        )


async def get_browser_context(playwright):
    """Launch browser and restore saved session."""
    _ensure_session_file()
    headless = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    browser = await playwright.chromium.launch(
        headless=headless,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = await browser.new_context(
        storage_state=SESSION_FILE,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800}
    )
    return browser, context


async def verify_logged_in(page):
    """Navigate to Facebook home and confirm we're logged in."""
    await page.goto("https://www.facebook.com", wait_until="domcontentloaded")
    await asyncio.sleep(2)
    if "login" in page.url or "checkpoint" in page.url:
        # Session expired — delete stale session file
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        raise RuntimeError(
            "Facebook session expired. Run `python save_session.py` again to refresh it."
        )
    print("Session valid — logged in.")


async def scrape_listing(listing_url: str) -> dict:
    """
    Scrape a single Facebook Marketplace listing URL.
    Returns the same shape as the Chrome extension's localScraperRoutine.
    """
    async with async_playwright() as playwright:
        browser, context = await get_browser_context(playwright)
        page = await context.new_page()

        try:
            # Verify session is still valid
            await verify_logged_in(page)

            # Navigate to the listing
            print(f"Navigating to: {listing_url}")
            await page.goto(listing_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            import re

            # --- Page text for regex extraction ---
            page_text = await page.evaluate("document.body.innerText || ''")

            # --- Title ---
            # page.title() is server-rendered and reliable: "(2) 2015 Ford Explorer - $6,000 | Facebook"
            raw_title = await page.title()
            title = re.sub(r"^\(\d+\)\s*", "", raw_title)          # strip notification count
            title = re.sub(r"\s*\|\s*Facebook$", "", title, flags=re.IGNORECASE)  # strip " | Facebook"
            title = re.sub(r"\s*-\s*\$[\d,]+$", "", title)         # strip " - $6,000" from end
            title = re.sub(r"^Marketplace\s*[-–]\s*", "", title, flags=re.IGNORECASE)  # strip "Marketplace - "
            title = title.strip()
            print(f"Raw page title: {raw_title!r}  →  extracted: {title!r}")

            # --- Price ---
            price = "Not Found"
            price_match = re.search(r'\$[0-9,]+', page_text)
            if price_match:
                price = price_match.group(0)

            # --- Mileage ---
            mileage = "Not Found"
            mileage_match = re.search(r'Driven\s+([0-9,]+)\s+miles', page_text, re.IGNORECASE)
            if mileage_match:
                mileage = mileage_match.group(1) + " miles"

            # --- Transmission ---
            transmission = "Not Found"
            if re.search(r'Automatic\s+transmission', page_text, re.IGNORECASE):
                transmission = "Automatic"
            elif re.search(r'Manual\s+transmission', page_text, re.IGNORECASE):
                transmission = "Manual"

            # --- Description ---
            description = ""
            og_desc = await page.evaluate("document.querySelector('meta[property=\"og:description\"]')?.content || ''")
            if og_desc and len(og_desc) > 15:
                description = og_desc
            else:
                description = page_text[:500]  # Fallback: first 500 chars

            # --- Photos: collect all scontent images then click through carousel ---
            seen_srcs = set()
            images = []

            def collect_new(srcs):
                for src in srcs:
                    if src not in seen_srcs:
                        seen_srcs.add(src)
                        images.append(src)

            GRAB_JS = """
                () => Array.from(document.querySelectorAll('img'))
                    .filter(img => img.src.includes('scontent'))
                    .map(img => img.src)
            """
            NEXT_JS = """
                () => {
                    const candidates = Array.from(document.querySelectorAll(
                        '[aria-label="Next photo"], [aria-label="Next image"], ' +
                        '[aria-label="Next"], div[role="button"]'
                    ));
                    for (const el of candidates) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.width < 100 && r.right > window.innerWidth / 2) {
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            return true;
                        }
                    }
                    return false;
                }
            """

            print("Collecting photos...")
            try:
                collect_new(await page.evaluate(GRAB_JS))
                for i in range(40):
                    prev = len(images)
                    try:
                        await page.evaluate(NEXT_JS)
                    except Exception:
                        pass
                    await asyncio.sleep(0.7)
                    try:
                        collect_new(await page.evaluate(GRAB_JS))
                    except Exception:
                        pass
                    if len(images) == prev and i > 3:
                        break
            except Exception as photo_err:
                print(f"Photo collection error (continuing): {photo_err}")

            print(f"Photos collected: {len(images)}")

            # --- Sold detection --- (re-read page text now that page is fully loaded)
            try:
                page_text = await page.evaluate("document.body.innerText || ''")
            except Exception:
                pass
            sold_phrases = [
                "mark as available",
                "this listing has been marked as sold",
                "this listing is no longer available",
                "item has been sold",
                "seller marked this as sold",
            ]
            page_text_lower = page_text.lower()
            is_sold = any(phrase in page_text_lower for phrase in sold_phrases)
            if is_sold:
                print(f"Listing is SOLD: {title}")

            print(f"Scraped '{title}' — {len(images)} images, sold={is_sold}")
            return {
                "success": True,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                "url": listing_url,
                "title": title,
                "price": price,
                "mileage": mileage,
                "transmission": transmission,
                "description": description or "No description found.",
                "images": images[:40],
                "is_sold": is_sold,
            }

        except Exception as e:
            print(f"Scrape error: {e}")
            return {"success": False, "error": str(e)}

        finally:
            await browser.close()
