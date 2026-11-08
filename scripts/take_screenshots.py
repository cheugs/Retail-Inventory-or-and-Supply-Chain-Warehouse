"""Take the README screenshots of the dashboard (uses the Edge browser already
installed on Windows through Playwright: pip install playwright).

    python -m uvicorn dashboard.app:app --port 8010   # in another terminal
    python scripts/take_screenshots.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8010/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"
SECTIONS = {"overview": "#overview", "stockouts": "#stockouts"}

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    # reduced motion: every block is shown at once, no animation in progress
    page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce", device_scale_factor=1)
    page.goto(URL, wait_until="load")
    page.wait_for_selector("#loader.done", state="attached")
    for name, anchor in SECTIONS.items():
        page.evaluate(f"document.querySelector('{anchor}').scrollIntoView()")
        page.mouse.wheel(0, 380)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / f"dashboard-{name}.png"))
        print("saved", name)
    browser.close()
