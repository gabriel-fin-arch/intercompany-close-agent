"""Record docs/img/demo.gif: the offline demo, then the reviewer dashboard.

Every frame comes from the code as it is. The first is the real output of
`cli demo`, drawn as text; the rest are screenshots of the Streamlit dashboard
running on the committed data, driven by Playwright: name the preparer, run
the close, reject one worklist item with a note and the rest without, name the
reviewer, submit. Every item needs a decision before the dashboard submits,
and rejecting is the one that books nothing, so the recording doesn't make an
accounting call on anyone's behalf. Run from the repo root with a Python that
has Playwright (and its Chromium) and Pillow:

    python scripts/record_demo.py

The app itself runs through uv, with ANTHROPIC_API_KEY set empty so triage is
the offline rules. Nothing here is part of the package or its tests.
"""

from __future__ import annotations

import io
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "demo.gif"
PORT = 8599
WIDTH, HEIGHT = 1280, 800
GIF_WIDTH = 960
# The item the recording shows a note on, and what it says. Every other item
# is rejected without a note. The names are made up, as in the tests.
ITEM = "ROYALTY-2025-1004"
NOTE = "No mirror leg in ZA01's manual load; asked ZA01 to re-key before booking."
PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"
OFFLINE = {**os.environ, "ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": ""}


def terminal_frame(command: list[str], prompt: str, lines: int = 30) -> Image.Image:
    out = subprocess.run(command, cwd=ROOT, env=OFFLINE, capture_output=True, text=True, check=True).stdout
    text = [f"$ {prompt}", ""] + out.splitlines()[:lines] + ["..."]
    try:
        font = ImageFont.truetype("consola.ttf", 17)
    except OSError:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 16)
    image = Image.new("RGB", (WIDTH, HEIGHT), "#1e1e1e")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(text):
        draw.text((24, 20 + i * 24), line[:130], font=font, fill="#9cdcfe" if i == 0 else "#d4d4d4")
    return image


def wait_for(url: str, seconds: float = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


def shot(page) -> Image.Image:
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def dashboard_frames() -> list[Image.Image]:
    server = subprocess.Popen(
        ["uv", "run", "streamlit", "run", "app/streamlit_app.py", "--server.headless", "true",
         "--server.port", str(PORT), "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal"],
        cwd=ROOT, env=OFFLINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    frames: list[Image.Image] = []
    try:
        wait_for(f"http://localhost:{PORT}/_stcore/health")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.goto(f"http://localhost:{PORT}")
            page.get_by_role("button", name="Run close pipeline").wait_for()
            # The relative path, rather than the absolute default, so the frame
            # doesn't show where the repo sits on this machine.
            page.get_by_role("textbox", name="Data folder or workbook", exact=True).fill("data/synthetic")
            page.get_by_role("textbox", name="Data folder or workbook", exact=True).press("Enter")
            page.get_by_role("textbox", name="Prepared by", exact=True).fill(PREPARER)
            page.get_by_role("textbox", name="Prepared by", exact=True).press("Enter")
            page.wait_for_timeout(1000)
            frames.append(shot(page))

            page.get_by_role("button", name="Run close pipeline").click()
            page.get_by_text("Reviewer worklist").wait_for(timeout=60_000)
            page.locator('[data-testid="stMetricValue"]').first.wait_for(timeout=60_000)
            page.wait_for_timeout(2000)
            frames.append(shot(page))

            items = page.locator('[data-testid="stExpander"]')
            for i in range(items.count()):
                items.nth(i).get_by_text("reject", exact=True).click()
                page.wait_for_timeout(300)
            item = items.filter(has_text=ITEM)
            item.get_by_role("textbox", name="Reviewer note").fill(NOTE)
            item.get_by_role("textbox", name="Reviewer note").press("Enter")
            page.wait_for_timeout(1500)
            item.scroll_into_view_if_needed()
            frames.append(shot(page))

            page.get_by_role("textbox", name="Reviewer", exact=True).fill(REVIEWER)
            page.get_by_role("textbox", name="Reviewer", exact=True).press("Enter")
            page.wait_for_timeout(1000)
            page.get_by_role("button", name="Submit decisions").click()
            page.get_by_text("Close finalized.").wait_for(timeout=60_000)
            page.wait_for_timeout(1000)
            page.get_by_text("Close finalized.").scroll_into_view_if_needed()
            frames.append(shot(page))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=20)
    return frames


def main() -> None:
    frames = [
        terminal_frame(
            ["uv", "run", "python", "-m", "intercompany_close_agent.cli", "demo"],
            "uv run python -m intercompany_close_agent.cli demo",
        )
    ]
    frames += dashboard_frames()
    small = [f.resize((GIF_WIDTH, round(f.height * GIF_WIDTH / f.width)), Image.LANCZOS) for f in frames]
    palette = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in small]
    durations = [5000, 3000, 5000, 5000, 6000][: len(palette)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    palette[0].save(OUT, save_all=True, append_images=palette[1:], duration=durations, loop=0, optimize=True)
    print(f"{OUT}: {len(palette)} frames, {sum(durations) / 1000:.0f} s, {OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
