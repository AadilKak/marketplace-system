"""
Run this ONCE to save your Facebook login session.
After this, the scraper uses the saved session automatically — no login needed again.

Usage:
    python save_session.py

A browser window will open. Log into Facebook manually, then come back
to this terminal and press Enter. Done.
"""

import asyncio
from playwright.async_api import async_playwright

SESSION_FILE = "fb_session.json"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login")

        print("\nA browser window just opened.")
        print("Log into your burner Facebook account manually.")
        print("Once you are logged in and see your feed, come back here.\n")
        input("Press Enter when you are logged in...")

        await context.storage_state(path=SESSION_FILE)
        print(f"\nSession saved to {SESSION_FILE}")
        print("You can now run: python test_scraper.py")
        await browser.close()

asyncio.run(main())
