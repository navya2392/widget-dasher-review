"""Render analysis.ipynb to a PDF of markdown + outputs only (no code cells), one PDF per phase.

Usage:
    .venv\\Scripts\\python export_pdf.py --phase 1              -> analysis_report_phase1.pdf  (section 1)
    .venv\\Scripts\\python export_pdf.py --phase 2              -> analysis_report_phase2.pdf  (sections 2-4)
    .venv\\Scripts\\python export_pdf.py --sections 6,7 -o x.pdf  (any explicit section list)
    .venv\\Scripts\\python export_pdf.py                        -> analysis_report.pdf (whole notebook)

Sections are the notebook's top-level "## N. Title" headers. The notebook is NOT re-executed here;
run it first so the stored outputs are current.

nbconvert's built-in webpdf exporter fails on Windows (asyncio subprocess NotImplementedError), so
this does the two steps by hand: nbconvert -> HTML with --no-input, then Playwright/Chromium prints
the HTML to PDF. Print CSS is injected so wide DataFrames shrink and wrap instead of clipping, and so
long tables split across pages instead of jumping whole. Every table is measured against the printable
width and any overflow is reported.
"""
import argparse
import asyncio
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import nbformat
from playwright.sync_api import sync_playwright

NOTEBOOK = Path(__file__).with_name("analysis.ipynb")

# CLAUDE.md phase -> notebook sections. Sections 6 (Q2 sizing) and 7 (Q3 baselines) are not yet
# assigned to a phase; export them with --sections when the time comes.
PHASES = {1: [1], 2: [2, 3, 4], 3: [5], 4: [8], 5: [9]}

PAGE = {"format": "A4", "margin": {"top": "14mm", "bottom": "14mm", "left": "11mm", "right": "11mm"}}
PRINTABLE_PX = round((210 - 22) / 25.4 * 96)  # A4 width minus side margins, in CSS px at 96 dpi

PRINT_CSS = """
@page { size: A4; margin: 14mm 11mm; }
html, body { width: %dpx !important; max-width: %dpx !important; }
body { font-size: 11px !important; }
/* nbconvert wraps outputs in flex boxes, which Chromium will not split across pages: make them blocks */
.jp-Notebook, .jp-Cell, .jp-Cell-inputWrapper, .jp-Cell-outputWrapper, .jp-OutputArea,
.jp-OutputArea-child, .jp-OutputArea-output, .jp-RenderedHTMLCommon, .jp-RenderedMarkdown {
  display: block !important; max-width: 100%% !important; overflow: visible !important;
  break-inside: auto !important; page-break-inside: auto !important;
  padding-left: 0 !important; padding-right: 0 !important;
  margin-left: 0 !important; margin-right: 0 !important; }
.jp-Notebook { padding: 0 !important; }
h1 { font-size: 20px !important; } h2 { font-size: 16px !important; }
h3 { font-size: 13px !important; } h4 { font-size: 12px !important; }
h2, h3, h4 { break-after: avoid; }
.jp-OutputArea-child .jp-RenderedMarkdown p { break-after: avoid; margin-bottom: 2px !important; }
.jp-RenderedHTMLCommon table { font-size: 8.5px !important; line-height: 1.25 !important;
  border-collapse: collapse !important; table-layout: auto !important; max-width: 100%% !important;
  margin-left: 0 !important; break-inside: auto !important; }
.jp-RenderedHTMLCommon th, .jp-RenderedHTMLCommon td { padding: 2px 4px !important;
  white-space: normal !important; vertical-align: top !important;
  /* "anywhere" lets long tokens (timestamps, column names) wrap so tables never overflow;
     NOWRAP_JS below pins short single-token cells (numbers, "expected", "yes") so they never split */
  overflow-wrap: anywhere !important; word-break: break-word !important; hyphens: none !important; }
.jp-RenderedHTMLCommon tr { break-inside: avoid; }
.jp-RenderedHTMLCommon thead { display: table-header-group; }
.jp-RenderedHTMLCommon pre, .jp-OutputArea-output pre { font-size: 8.5px !important;
  white-space: pre-wrap !important; overflow-wrap: anywhere !important; }
/* markdown tables (definitions, cleaning log): keep the narrow first column from wrapping digits */
.jp-RenderedMarkdown table { font-size: 9px !important; }
.jp-RenderedMarkdown td:first-child, .jp-RenderedMarkdown th:first-child { white-space: nowrap !important; }
""" % (PRINTABLE_PX, PRINTABLE_PX)

NOWRAP_JS = """
() => {
  let n = 0;
  document.querySelectorAll('table td, table th').forEach(c => {
    const t = c.innerText.trim();
    if (t.length > 0 && t.length <= 16 && !/\s/.test(t)) { c.style.whiteSpace = 'nowrap'; n++; }
  });
  return n;
}
"""

OVERFLOW_PROBE = """
() => {
  const limit = document.documentElement.clientWidth;
  return Array.from(document.querySelectorAll('table')).map((t, i) => {
    const r = t.getBoundingClientRect();
    const head = (t.querySelector('th, td') || {}).innerText || '';
    return {i, width: Math.round(r.width), right: Math.round(r.right), limit,
            overflow: r.right > limit + 1, head: head.slice(0, 40)};
  });
}
"""

SECTION_RE = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)


def select_sections(nb, wanted, subtitle):
    """Keep the title cell, add a subtitle, keep only cells under the wanted '## N.' headers."""
    out = nbformat.v4.new_notebook(metadata=nb.metadata)
    current = None
    titles = {}
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            m = SECTION_RE.match(cell.source)
            if m:
                current = int(m.group(1))
                titles[current] = m.group(2)
        if current is None or current in wanted:
            out.cells.append(cell)
    missing = [s for s in wanted if s not in titles]
    if missing:
        sys.exit(f"sections not found in notebook: {missing}")
    names = ", ".join(titles[s] for s in wanted)
    out.cells.insert(1, nbformat.v4.new_markdown_cell(f"*{subtitle}: {names}*"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", type=int, choices=sorted(PHASES))
    ap.add_argument("--sections", help="comma-separated section numbers, e.g. 2,3,4")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    nb = nbformat.read(NOTEBOOK, as_version=4)
    if args.sections:
        wanted = [int(s) for s in args.sections.split(",")]
        nb = select_sections(nb, wanted, "Sections")
        default_out = "analysis_report_sections_" + "-".join(map(str, wanted)) + ".pdf"
    elif args.phase:
        nb = select_sections(nb, PHASES[args.phase], f"Phase {args.phase}")
        default_out = f"analysis_report_phase{args.phase}.pdf"
    else:
        default_out = "analysis_report.pdf"
    out_pdf = Path(args.output) if args.output else NOTEBOOK.with_name(default_out)

    with tempfile.TemporaryDirectory() as tmp:
        nb_path = Path(tmp) / "selected.ipynb"
        nbformat.write(nb, nb_path)
        subprocess.run(
            [sys.executable, "-m", "nbconvert", "--to", "html", "--no-input", "--no-prompt",
             "--output", "selected", "--output-dir", tmp, str(nb_path)],
            check=True,
        )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": PRINTABLE_PX, "height": 1200})
            page.goto((Path(tmp) / "selected.html").resolve().as_uri())
            page.wait_for_load_state("networkidle")
            page.add_style_tag(content=PRINT_CSS)
            page.emulate_media(media="print")
            page.evaluate(NOWRAP_JS)
            tables = page.evaluate(OVERFLOW_PROBE)
            page.pdf(path=str(out_pdf), print_background=True, prefer_css_page_size=True, **PAGE)
            browser.close()

    bad = [t for t in tables if t["overflow"]]
    print(f"wrote {out_pdf}")
    print(f"tables: {len(tables)} | printable width: {PRINTABLE_PX}px | overflowing: {len(bad)}")
    for t in bad:
        print(f"  OVERFLOW table #{t['i']}: right edge {t['right']}px > {t['limit']}px (starts: {t['head']!r})")
    if tables:
        widest = max(tables, key=lambda t: t["width"])
        print(f"widest table: #{widest['i']} at {widest['width']}px (starts: {widest['head']!r})")


if __name__ == "__main__":
    main()
