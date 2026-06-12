"""
Quick test — runs the Playwright scraper directly against a real Marketplace URL.
No Chrome extension, no server needed.

Usage:
  1. Run `python save_session.py` first (one-time setup, logs you in manually)
  2. python test_scraper.py
"""

import asyncio
import json
from scraper import scrape_listing

# Paste any live Facebook Marketplace listing URL here to test
TEST_URL = "https://www.facebook.com/marketplace/item/2331515890707232/"

async def main():
    print(f"\n{'='*60}")
    print(f"Testing scraper against:")
    print(f"  {TEST_URL}")
    print(f"{'='*60}\n")

    result = await scrape_listing(TEST_URL)

    print(f"\n{'='*60}")
    if result.get("success"):
        print(f"✓ SUCCESS\n")
        print(f"  Title:        {result['title']}")
        print(f"  Price:        {result['price']}")
        print(f"  Mileage:      {result['mileage']}")
        print(f"  Transmission: {result['transmission']}")
        print(f"  Images found: {len(result['images'])}")
        print(f"  Description:  {result['description'][:100]}...")
        print(f"\nFirst image URL:\n  {result['images'][0] if result['images'] else 'None'}")
    else:
        print(f"✗ FAILED")
        print(f"  Error: {result.get('error')}")

    print(f"\n{'='*60}")
    print("Full result saved to: test_result.json")
    with open("test_result.json", "w") as f:
        json.dump(result, f, indent=2)

asyncio.run(main())
