import asyncio
import os
from playwright.async_api import async_playwright

# Burner account credentials — set these as environment variables on Render
FB_EMAIL = os.environ.get("FB_EMAIL", "")
FB_PASSWORD = os.environ.get("FB_PASSWORD", "")

# Path to store the saved login session so we don't re-login every time
SESSION_FILE = "fb_session.json"


async def get_browser_context(playwright):
    """Launch browser and restore saved session if available."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )

    # Restore saved cookies/session if we have one
    if os.path.exists(SESSION_FILE):
        context = await browser.new_context(storage_state=SESSION_FILE)
    else:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )

    return browser, context


async def login_if_needed(page):
    """Log in to Facebook with burner account if not already logged in."""
    await page.goto("https://www.facebook.com", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # Check if already logged in
    if "login" not in page.url and await page.query_selector('[aria-label="Your profile"]'):
        print("Already logged in.")
        return True

    print("Logging in to Facebook...")
    try:
        await page.fill('input[name="email"]', FB_EMAIL)
        await page.fill('input[name="pass"]', FB_PASSWORD)
        await page.click('button[name="login"]')
        await asyncio.sleep(4)

        # Save session for next time
        await page.context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        return False


async def scrape_listing(listing_url: str) -> dict:
    """
    Scrape a single Facebook Marketplace listing URL.
    Returns the same shape as the Chrome extension's localScraperRoutine.
    """
    async with async_playwright() as playwright:
        browser, context = await get_browser_context(playwright)
        page = await context.new_page()

        try:
            # Login if needed
            logged_in = await login_if_needed(page)
            if not logged_in:
                return {"success": False, "error": "Facebook login failed. Check FB_EMAIL and FB_PASSWORD env vars."}

            # Navigate to the listing
            print(f"Navigating to: {listing_url}")
            await page.goto(listing_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # --- Title ---
            title = ""
            og_title = await page.evaluate("document.querySelector('meta[property=\"og:title\"]')?.content || ''")
            if og_title:
                title = og_title
            else:
                h1 = await page.query_selector("h1")
                if h1:
                    title = await h1.inner_text()

            # Clean up title
            import re
            title = re.sub(r"^\(\d+\)\s*Marketplace\s*-\s*", "", title, flags=re.IGNORECASE)
            title = re.sub(r"\s*\|\s*Facebook$", "", title, flags=re.IGNORECASE).strip()

            # --- Page text for regex extraction ---
            page_text = await page.evaluate("document.body.innerText || ''")

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

            # --- Photos: click through carousel ---
            images = []
            seen_srcs = set()

            async def capture_images():
                img_srcs = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('img'))
                        .filter(img => img.src.includes('scontent') && img.naturalWidth >= 50 && img.naturalHeight >= 50)
                        .map(img => img.src)
                """)
                for src in img_srcs:
                    if src not in seen_srcs:
                        seen_srcs.add(src)
                        images.append(src)

            await capture_images()

            # Click through carousel up to 40 times
            for i in range(40):
                # Try to find a Next button near the main image
                next_btn = await page.evaluate("""
                    () => {
                        const btns = Array.from(document.querySelectorAll('div[role="button"], button, [aria-label*="Next"], [aria-label*="next"]'));
                        const mainImg = Array.from(document.querySelectorAll('img'))
                            .filter(img => img.naturalWidth > 250)
                            .sort((a, b) => (b.getBoundingClientRect().width * b.getBoundingClientRect().height) - (a.getBoundingClientRect().width * a.getBoundingClientRect().height))[0];
                        if (!mainImg) return null;
                        const imgRect = mainImg.getBoundingClientRect();
                        const midY = imgRect.top + imgRect.height / 2;
                        const btn = btns.find(el => {
                            const r = el.getBoundingClientRect();
                            if (r.width === 0 || r.width > 120) return false;
                            const cx = r.left + r.width / 2;
                            const cy = r.top + r.height / 2;
                            return Math.abs(cy - midY) < 120 && cx > imgRect.left + imgRect.width * 0.5;
                        });
                        return btn ? true : false;
                    }
                """)

                if next_btn:
                    await page.evaluate("""
                        () => {
                            const btns = Array.from(document.querySelectorAll('div[role="button"], button, [aria-label*="Next"], [aria-label*="next"]'));
                            const mainImg = Array.from(document.querySelectorAll('img'))
                                .filter(img => img.naturalWidth > 250)
                                .sort((a, b) => (b.getBoundingClientRect().width * b.getBoundingClientRect().height) - (a.getBoundingClientRect().width * a.getBoundingClientRect().height))[0];
                            if (!mainImg) return;
                            const imgRect = mainImg.getBoundingClientRect();
                            const midY = imgRect.top + imgRect.height / 2;
                            const btn = btns.find(el => {
                                const r = el.getBoundingClientRect();
                                if (r.width === 0 || r.width > 120) return false;
                                const cx = r.left + r.width / 2;
                                const cy = r.top + r.height / 2;
                                return Math.abs(cy - midY) < 120 && cx > imgRect.left + imgRect.width * 0.5;
                            });
                            if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        }
                    """)
                else:
                    # Fallback: arrow key
                    await page.keyboard.press("ArrowRight")

                await asyncio.sleep(0.9)
                prev_count = len(images)
                await capture_images()

                # Stop if no new images appeared
                if len(images) == prev_count and i > 2:
                    break

            print(f"Scraped '{title}' — {len(images)} images found.")
            return {
                "success": True,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                "url": listing_url,
                "title": title,
                "price": price,
                "mileage": mileage,
                "transmission": transmission,
                "description": description or "No description found.",
                "images": images[:40]
            }

        except Exception as e:
            print(f"Scrape error: {e}")
            return {"success": False, "error": str(e)}

        finally:
            await browser.close()
