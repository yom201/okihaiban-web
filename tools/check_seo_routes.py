#!/usr/bin/env python3
"""Fail when the LP regains soft-404s, duplicate aliases, or broken SEO routes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
CANONICAL_ORIGIN = "https://okihaiban.com"
PAGES_ORIGIN = "https://okihaiban-web.pages.dev"
REQUIRED_ALIASES = {
    "/bannosuke": "/",
    "/bannosuke.html": "/",
    "/eula": "/terms-of-use",
    "/eula.html": "/terms-of-use",
}
RETIRED_ALIAS_FILES = (PUBLIC / "bannosuke.html", PUBLIC / "eula.html")


@dataclass
class Page:
    title: str = ""
    description: str = ""
    canonical: str = ""
    robots: str = ""
    h1_count: int = 0
    hrefs: list[str] = field(default_factory=list)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page = Page()
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = values.get("name", "").lower()
            if name == "description":
                self.page.description = values.get("content", "").strip()
            elif name == "robots":
                self.page.robots = values.get("content", "").lower()
        elif tag == "link" and values.get("rel", "").lower() == "canonical":
            self.page.canonical = values.get("href", "").strip()
        elif tag == "h1":
            self.page.h1_count += 1
        elif tag == "a" and values.get("href"):
            self.page.hrefs.append(values["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page.title += data.strip()


def parse_page(path: Path) -> Page:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.page


def route_file(route: str) -> Path:
    if route == "/":
        return PUBLIC / "index.html"
    return PUBLIC / f"{route.lstrip('/')}.html"


def parse_redirects() -> dict[str, tuple[str, str]]:
    redirects: dict[str, tuple[str, str]] = {}
    path = PUBLIC / "_redirects"
    if not path.exists():
        return redirects
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 3:
            redirects[parts[0]] = (parts[1], parts[2])
    return redirects


def sitemap_entries() -> list[tuple[str, str]]:
    root = ET.parse(PUBLIC / "sitemap.xml").getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries: list[tuple[str, str]] = []
    for item in root.findall("sm:url", ns):
        loc = (item.findtext("sm:loc", default="", namespaces=ns)).strip()
        lastmod = (item.findtext("sm:lastmod", default="", namespaces=ns)).strip()
        entries.append((loc, lastmod))
    return entries


def internal_route(href: str) -> str | None:
    if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
        return None
    parsed = urlparse(urljoin(f"{CANONICAL_ORIGIN}/", href))
    if parsed.netloc != "okihaiban.com":
        return None
    return parsed.path or "/"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


NO_REDIRECT = build_opener(NoRedirect)


def first_response(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "okihaiban-seo-gate/1.0"})
    try:
        response = NO_REDIRECT.open(request, timeout=15)
        return response.status, response.headers.get("Location", "")
    except HTTPError as error:
        return error.code, error.headers.get("Location", "")


def final_response(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "okihaiban-seo-gate/1.0"})
    try:
        response = urlopen(request, timeout=15)
        return response.status, response.geturl()
    except HTTPError as error:
        return error.code, error.geturl()


def source_audit() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    entries = sitemap_entries()
    urls = [loc for loc, _ in entries]
    if not urls:
        errors.append("sitemap.xml has no URLs")
        return errors, notes
    if len(urls) != len(set(urls)):
        errors.append("sitemap.xml contains duplicate URLs")

    pages: dict[str, Page] = {}
    incoming = {urlparse(url).path or "/": 0 for url in urls}
    titles: dict[str, str] = {}
    today = date.today()

    for loc, lastmod in entries:
        parsed = urlparse(loc)
        route = parsed.path or "/"
        if f"{parsed.scheme}://{parsed.netloc}" != CANONICAL_ORIGIN:
            errors.append(f"non-canonical sitemap host: {loc}")
        path = route_file(route)
        if not path.exists():
            errors.append(f"missing HTML for sitemap route {route}: {path.relative_to(ROOT)}")
            continue
        page = parse_page(path)
        pages[route] = page
        if page.canonical != loc:
            errors.append(f"canonical mismatch for {route}: {page.canonical or '[missing]'}")
        if not page.title:
            errors.append(f"missing title for {route}")
        elif page.title in titles:
            errors.append(f"duplicate sitemap title for {route} and {titles[page.title]}")
        else:
            titles[page.title] = route
        if not page.description:
            errors.append(f"missing meta description for {route}")
        if page.h1_count != 1:
            errors.append(f"expected one h1 for {route}, found {page.h1_count}")
        try:
            modified = date.fromisoformat(lastmod)
            if modified > today:
                errors.append(f"future sitemap lastmod for {route}: {lastmod}")
        except ValueError:
            errors.append(f"invalid sitemap lastmod for {route}: {lastmod or '[missing]'}")

    for html_path in PUBLIC.glob("*.html"):
        page = parse_page(html_path)
        for href in page.hrefs:
            route = internal_route(href)
            if route in incoming:
                incoming[route] += 1

    for route, count in incoming.items():
        if route != "/" and count == 0:
            errors.append(f"sitemap route has no internal incoming link: {route}")

    not_found = PUBLIC / "404.html"
    if not not_found.exists():
        errors.append("missing public/404.html; Cloudflare Pages will soft-200 unknown routes")
    else:
        page_404 = parse_page(not_found)
        if "noindex" not in page_404.robots:
            errors.append("public/404.html must be noindex")
        if page_404.canonical:
            errors.append("public/404.html must not declare a canonical URL")

    redirects = parse_redirects()
    for source, destination in REQUIRED_ALIASES.items():
        actual = redirects.get(source)
        if actual != (destination, "301"):
            errors.append(f"missing one-hop 301: {source} -> {destination}")
    for path in RETIRED_ALIAS_FILES:
        if path.exists():
            errors.append(f"retired alias must not remain as an HTML asset: {path.relative_to(ROOT)}")

    notes.append(f"SITEMAP_URLS={len(entries)}")
    notes.append(f"CANONICAL_TITLES={len(titles)}")
    notes.append(f"PERMANENT_ALIASES={len(REQUIRED_ALIASES)}")
    notes.append("SOFT_404_GUARD=public/404.html")
    return errors, notes


def live_audit() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    for loc, _ in sitemap_entries():
        status, final_url = final_response(loc)
        if status != 200 or final_url.rstrip("/") != loc.rstrip("/"):
            errors.append(f"live canonical route failed: {loc} -> {status} {final_url}")

    unknown = f"{CANONICAL_ORIGIN}/__seo_gate_missing_page__"
    status, _ = first_response(unknown)
    if status != 404:
        errors.append(f"unknown live route must return 404, got {status}: {unknown}")

    for source, destination in REQUIRED_ALIASES.items():
        status, location = first_response(f"{CANONICAL_ORIGIN}{source}")
        resolved = urljoin(f"{CANONICAL_ORIGIN}{source}", location)
        expected = f"{CANONICAL_ORIGIN}{destination}"
        if status != 301 or resolved.rstrip("/") != expected.rstrip("/"):
            errors.append(f"live alias must be one 301 hop: {source} -> {status} {location or '[none]'}")

    for origin in ("https://www.okihaiban.com", PAGES_ORIGIN):
        status, location = first_response(f"{origin}/")
        resolved = urljoin(f"{origin}/", location)
        if status not in (301, 308) or resolved != f"{CANONICAL_ORIGIN}/":
            errors.append(f"duplicate host must redirect to canonical: {origin} -> {status} {location or '[none]'}")

    notes.append(f"LIVE_CANONICAL_URLS={len(sitemap_entries())}")
    notes.append("LIVE_UNKNOWN_STATUS=404")
    notes.append(f"LIVE_ALIAS_REDIRECTS={len(REQUIRED_ALIASES)}")
    notes.append("LIVE_HOST_REDIRECTS=www,pages.dev")
    return errors, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="also verify the deployed Cloudflare site")
    args = parser.parse_args()

    errors, notes = source_audit()
    if args.live:
        live_errors, live_notes = live_audit()
        errors.extend(live_errors)
        notes.extend(live_notes)

    for note in notes:
        print(note)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"SEO_ROUTE_GATE=FAIL errors={len(errors)}", file=sys.stderr)
        return 1
    print("SEO_ROUTE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
