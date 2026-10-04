#!/usr/bin/env python3
"""Check wide-screen section content alignment using Chrome and the stdlib."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from functools import partial
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
import xml.etree.ElementTree as ET


PUBLIC = Path(__file__).resolve().parents[1] / "public"
WIDTHS = (2000, 1440)
INJECTION = (
    "\n@media (min-width:1100px){.response-landing .response-hero"
    "{padding-inline:112px !important}}\n"
)


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    ]
    for candidate in candidates:
        if candidate:
            executable = shutil.which(candidate)
            if executable:
                return executable
    raise ValueError("Chrome not found (set CHROME to an executable)")


def sitemap_pages(root: Path) -> list[tuple[str, str]]:
    root = root.resolve()
    tree = ET.parse(root / "sitemap.xml")
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages = []
    for loc in tree.findall("s:url/s:loc", namespace):
        if not loc.text or not loc.text.strip():
            raise ValueError("sitemap contains an empty URL")
        path = unquote(urlsplit(loc.text.strip()).path) or "/"
        filename = "index.html" if path == "/" else path.lstrip("/") + ".html"
        target = (root / filename).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"sitemap path escapes root: {path}")
        pages.append((path, filename))
    if not pages:
        raise ValueError("sitemap contains no URLs")
    return pages


def measurement_html(filename: str, width: int) -> bytes:
    source = html.escape("/" + quote(filename, safe="/"), quote=True)
    return ("""<!doctype html><html><head><meta charset="utf-8">
<title>ALIGNMENT_PENDING</title></head><body style="margin:0">
<script>
function measure(frame) {
  try {
    const doc = frame.contentDocument;
    const blocks = [...new Set(doc.querySelectorAll('main > section, body > section'))];
    const results = [];
    for (const block of blocks) {
      const lefts = [...block.querySelectorAll('h1,h2,h3,p,li,img,table,a,figure')]
        .map(element => element.getBoundingClientRect())
        .filter(rect => rect.width > 0 && rect.height > 0)
        .map(rect => rect.left);
      if (lefts.length) results.push({
        block: block.tagName.toLowerCase() + [...block.classList].map(c => '.' + c).join(''),
        left: Math.min(...lefts)
      });
    }
    document.title = JSON.stringify({width: frame.clientWidth, blocks: results});
  } catch (error) {
    document.title = JSON.stringify({error: String(error)});
  }
}
</script>
""" + f'<iframe src="{source}" style="display:block;border:0;width:{width}px;'
            'height:3000px" onload="measure(this)"></iframe></body></html>').encode("utf-8")


class MeasurementHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/__measure":
            # Extensionless internal links use the same HTML mapping as the sitemap.
            relative = unquote(parsed.path).lstrip("/")
            if relative and not Path(relative).suffix:
                target = (Path(self.directory) / (relative + ".html")).resolve()
                if target.is_relative_to(Path(self.directory).resolve()) and target.is_file():
                    self.path = quote("/" + relative + ".html", safe="/")
            return super().do_GET()
        try:
            query = parse_qs(parsed.query)
            filename = query["page"][0]
            width = int(query["w"][0])
            root = Path(self.directory).resolve()
            target = (root / filename).resolve()
            if width not in WIDTHS or not target.is_relative_to(root) or not target.is_file():
                raise ValueError("invalid measurement target")
        except (KeyError, ValueError):
            self.send_error(400, "Invalid measurement request")
            return
        content = measurement_html(filename, width)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


@contextmanager
def local_server(root: Path):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(MeasurementHandler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join()
        server.server_close()


def measure(chrome: str, origin: str, filename: str, width: int) -> list[dict]:
    url = origin + "/__measure?" + urlencode({"page": filename, "w": width})
    # Do not pass --user-data-dir: with a fresh profile, headless Chrome on macOS
    # prints the DOM but never exits, so every page times out (measured 2026-10-05).
    result = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu",
         f"--window-size={width + 50},3200", "--virtual-time-budget=5000",
         "--dump-dom", url],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        detail = result.stderr.strip()[-800:]
        raise ValueError(f"Chrome exited {result.returncode}: {detail}")
    title = re.search(r"<title[^>]*>(.*?)</title>", result.stdout, re.S | re.I)
    if not title:
        raise ValueError("measurement JSON title missing")
    data = json.loads(html.unescape(title.group(1)))
    if not isinstance(data, dict) or data.get("width") != width:
        raise ValueError(f"invalid measurement or iframe width: {data!r}")
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("measurement blocks missing")
    for block in blocks:
        if (not isinstance(block, dict) or not isinstance(block.get("block"), str)
                or type(block.get("left")) not in (int, float)
                or not math.isfinite(block["left"])):
            raise ValueError("invalid block measurement")
    return blocks


def alignment_errors(path: str, width: int, blocks: list[dict]) -> list[str]:
    if len(blocks) < 2:
        return [f"ERROR: {path} @{width}px: fewer than 2 measurable blocks ({len(blocks)})"]
    counts = Counter(math.floor(block["left"] / 4 + 0.5) * 4 for block in blocks)
    mode = max(counts, key=lambda left: (counts[left], left))
    return [
        f"ERROR: {path} @{width}px: {block['block']} content starts at "
        f"{block['left']:g}px, {mode - block['left']:g}px left of the page's "
        f"body sections ({mode:g}px)"
        for block in blocks if block["left"] < mode - 60
    ]


def run_gate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    measured = 0
    try:
        pages = sitemap_pages(root)
    except (OSError, ValueError, ET.ParseError) as error:
        pages = []
        errors.append(f"ERROR: cannot read sitemap: {error}")
    try:
        chrome = find_chrome()
        if pages:
            with local_server(root) as origin:
                for path, filename in pages:
                    page_measured = True
                    for width in WIDTHS:
                        try:
                            if not (root / filename).is_file():
                                raise ValueError(f"HTML missing: {filename}")
                            blocks = measure(chrome, origin, filename, width)
                            errors.extend(alignment_errors(path, width, blocks))
                            if len(blocks) < 2:
                                page_measured = False
                        except (OSError, ValueError, subprocess.SubprocessError) as error:
                            errors.append(f"ERROR: {path} @{width}px: {error}")
                            page_measured = False
                    measured += int(page_measured)
    except (OSError, ValueError) as error:
        errors.append(f"ERROR: {error}")
    print(f"ALIGNMENT_PAGES_MEASURED={measured}")
    if measured != len(pages):
        errors.append(f"ERROR: measured {measured} pages; sitemap contains {len(pages)} URLs")
    for error in errors:
        print(error)
    print(f"SECTION_ALIGNMENT_GATE=FAIL errors={len(errors)}" if errors
          else "SECTION_ALIGNMENT_GATE=PASS")
    return errors


def self_test(root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="alignment-self-test-") as temporary:
        copied = Path(temporary) / "public"
        shutil.copytree(root, copied)
        print("SELF_TEST phase=baseline")
        baseline = run_gate(copied)
        if baseline:
            print("SELF_TEST broken=UNVERIFIED restored=FAIL")
            return 1
        css = copied / "package-theft-response.css"
        original = css.read_bytes()
        try:
            css.write_bytes(original + INJECTION.encode("utf-8"))
            print("SELF_TEST phase=broken")
            broken = run_gate(copied)
        finally:
            css.write_bytes(original)
        print("SELF_TEST phase=restored")
        restored = run_gate(copied)
        detected = any(
            error.startswith("ERROR: /package-theft-response @")
            and "section.response-hero content starts at" in error
            for error in broken
        )
        success = detected and not restored
        print(f"SELF_TEST broken={'RED' if detected else 'FAIL'} "
              f"restored={'GREEN' if not restored else 'FAIL'}")
        return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PUBLIC, help="public directory to measure")
    parser.add_argument("--self-test", action="store_true", help="inject a defect in a temporary copy")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.self_test:
        try:
            result = self_test(root)
        except (OSError, ValueError) as error:
            print(f"ERROR: self-test: {error}")
            print("SELF_TEST broken=UNVERIFIED restored=FAIL")
            result = 1
        print("SECTION_ALIGNMENT_GATE=FAIL errors=1" if result
              else "SECTION_ALIGNMENT_GATE=PASS")
        return result
    return 1 if run_gate(root) else 0


if __name__ == "__main__":
    raise SystemExit(main())
