"""Render analysis.ipynb to a PDF of markdown + outputs only (no code cells).

Usage:  .venv\\Scripts\\python export_pdf.py [output.pdf]

nbconvert's built-in webpdf exporter fails on Windows (asyncio subprocess
NotImplementedError), so this does the two steps by hand: nbconvert -> HTML with
--no-input, then Playwright/Chromium prints the HTML to PDF.
"""
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

NOTEBOOK = Path(__file__).with_name("analysis.ipynb")
OUT_PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else NOTEBOOK.with_name("analysis_report.pdf")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

with tempfile.TemporaryDirectory() as tmp:
    html_path = Path(tmp) / "analysis.html"
    subprocess.run(
        [sys.executable, "-m", "nbconvert", "--to", "html", "--no-input", "--no-prompt",
         "--output", html_path.stem, "--output-dir", tmp, str(NOTEBOOK)],
        check=True,
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "15mm", "bottom": "15mm", "left": "12mm", "right": "12mm"},
        )
        browser.close()

print(f"wrote {OUT_PDF}")
