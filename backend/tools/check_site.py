"""Crawl the built site and assert the things that silently rot.

Meta tags, canonical URLs, sitemaps and internal links are exactly the kind of
thing nobody notices is broken, because nothing fails: the page still renders,
the crawler just quietly indexes the wrong URL or drops the page. So this is a
harness rather than a checklist.

    python backend/tools/check_site.py

It runs the real application against the real build, so a route that exists in
vite.config.ts but not in the server -- or the reverse -- is a failure here
rather than a 404 in production.
"""

from __future__ import annotations

import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DIST = ROOT.parent / "frontend" / "dist"

#: A page that is worth indexing but has no description is a page whose search
#: result is a fragment of its own navigation.
REQUIRED_META = ("description",)
MAX_TITLE = 65
MAX_DESCRIPTION = 165

failures: list[str] = []
warnings: list[str] = []


def fail(page: str, message: str) -> None:
    failures.append(f"{page}: {message}")


def warn(page: str, message: str) -> None:
    warnings.append(f"{page}: {message}")


def _squash(text: str) -> str:
    """Compare prose ignoring whitespace and entity differences."""
    return " ".join(html.unescape(text).split()).lower()


def _visible_text(doc: str) -> str:
    """What a reader actually sees.

    Script and style bodies have to go first. Leaving them in was a real bug
    in this file: the JSON-LD block is itself part of the document, so a check
    that FAQ questions appear "on the page" matched them against their own
    schema and could never fail.
    """
    without_code = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>", " ", doc, flags=re.S | re.I
    )
    return re.sub(r"<[^>]+>", " ", without_code)


def attr(tag: str, name: str) -> str | None:
    match = re.search(rf'{name}="([^"]*)"', tag)
    return html.unescape(match.group(1)) if match else None


def meta(doc: str, key: str, kind: str = "name") -> str | None:
    for tag in re.findall(r"<meta\b[^>]*>", doc):
        if attr(tag, kind) == key:
            return attr(tag, "content")
    return None


def main() -> int:
    if not DIST.is_dir():
        print(f"no build at {DIST}\nrun: cd frontend && npm run build")
        return 1

    from fastapi.testclient import TestClient
    from algostudio.api.app import ROUTES, create_app

    client = TestClient(create_app())

    # ---------------------------------------------------------------- pages
    titles: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    internal_links: set[tuple[str, str]] = set()

    for url in ROUTES:
        response = client.get(url)
        if response.status_code != 200:
            fail(url, f"expected 200, got {response.status_code}")
            continue
        doc = response.text

        # -- title -------------------------------------------------------
        match = re.search(r"<title>(.*?)</title>", doc, re.S)
        title = html.unescape(match.group(1).strip()) if match else ""
        if not title:
            fail(url, "no <title>")
        else:
            if len(title) > MAX_TITLE:
                warn(url, f"title is {len(title)} chars (>{MAX_TITLE}); it will be truncated")
            if title in titles:
                fail(url, f"title duplicates {titles[title]}")
            titles[title] = url

        # -- description -------------------------------------------------
        for key in REQUIRED_META:
            if not meta(doc, key):
                fail(url, f"no meta {key}")
        description = meta(doc, "description") or ""
        if description:
            if len(description) > MAX_DESCRIPTION:
                warn(url, f"description is {len(description)} chars (>{MAX_DESCRIPTION})")
            if description in descriptions:
                fail(url, f"description duplicates {descriptions[description]}")
            descriptions[description] = url

        # -- canonical ---------------------------------------------------
        canonical = None
        for tag in re.findall(r"<link\b[^>]*>", doc):
            if attr(tag, "rel") == "canonical":
                canonical = attr(tag, "href")
        if not canonical:
            fail(url, "no canonical link")
        else:
            path = urlparse(canonical).path or "/"
            if path != url:
                fail(url, f"canonical points at {path!r}, not {url!r}")
            if not canonical.startswith("http"):
                fail(url, "canonical must be absolute")
            if "%SITE_URL%" in canonical:
                fail(url, "canonical still contains the build placeholder")

        # -- one h1, in order --------------------------------------------
        headings = [int(h) for h in re.findall(r"<h([1-6])\b", doc)]
        h1s = headings.count(1)
        if h1s != 1:
            fail(url, f"{h1s} <h1> elements; exactly one is required")
        for previous, current in zip(headings, headings[1:]):
            if current > previous + 1:
                fail(url, f"heading jumps from h{previous} to h{current}")

        # -- images have alt ---------------------------------------------
        for tag in re.findall(r"<img\b[^>]*>", doc):
            if attr(tag, "alt") is None:
                fail(url, f"<img> without an alt attribute: {tag[:70]}")

        # -- social ------------------------------------------------------
        for key in ("og:title", "og:description", "og:image", "og:url"):
            if not meta(doc, key, kind="property"):
                warn(url, f"no {key}")
        if meta(doc, "og:image", kind="property") and not meta(
            doc, "og:image:alt", kind="property"
        ):
            warn(url, "og:image has no og:image:alt")

        # -- leftovers ---------------------------------------------------
        for placeholder in ("%SITE_URL%", "%YEAR%", "<!--ANALYTICS-->", "lorem ipsum"):
            if placeholder in doc:
                fail(url, f"unsubstituted {placeholder!r} in the served HTML")

        # -- structured data ----------------------------------------------
        # A malformed JSON-LD block fails completely silently: the page looks
        # fine and the rich result simply never appears.
        for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', doc, re.S
        ):
            try:
                data = json.loads(block)
            except json.JSONDecodeError as exc:
                fail(url, f"JSON-LD does not parse: {exc}")
                continue
            nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
            for node in nodes:
                if not isinstance(node, dict) or not node.get("@type"):
                    fail(url, "JSON-LD node without an @type")
                # Google requires FAQ answers to be visible on the page they
                # are declared on. Declaring more than is shown is a manual
                # action, not a warning.
                if node.get("@type") == "FAQPage":
                    text = _visible_text(doc)
                    for entry in node.get("mainEntity", []):
                        question = entry.get("name", "")
                        if question and _squash(question) not in _squash(text):
                            fail(url, f"FAQ schema declares a question that is "
                                      f"not visible: {question!r}")

        # -- collect links ------------------------------------------------
        for tag in re.findall(r"<a\b[^>]*>", doc):
            href = attr(tag, "href")
            if not href or href.startswith(("http", "mailto:", "#")):
                continue
            internal_links.add((url, href))

    # ------------------------------------------------------------- links
    for source, href in sorted(internal_links):
        target = href.split("#")[0] or "/"
        response = client.get(target)
        if response.status_code != 200:
            fail(source, f"broken internal link to {href} ({response.status_code})")

    # ----------------------------------------------------------- sitemap
    sitemap = client.get("/sitemap.xml")
    if sitemap.status_code != 200:
        fail("/sitemap.xml", f"not served ({sitemap.status_code})")
    else:
        try:
            tree = ET.fromstring(sitemap.text)
        except ET.ParseError as exc:
            fail("/sitemap.xml", f"is not valid XML: {exc}")
        else:
            ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
            listed = {
                urlparse(loc.text or "").path or "/"
                for loc in tree.iter(f"{ns}loc")
            }
            for path in sorted(listed):
                if client.get(path).status_code != 200:
                    fail("/sitemap.xml", f"lists {path}, which does not return 200")
            missing = set(ROUTES) - listed
            if missing:
                fail("/sitemap.xml", f"does not list served page(s): {sorted(missing)}")
            if "%SITE_URL%" in sitemap.text:
                fail("/sitemap.xml", "still contains the build placeholder")

    # ------------------------------------------------------------ robots
    robots = client.get("/robots.txt")
    if robots.status_code != 200:
        fail("/robots.txt", f"not served ({robots.status_code})")
    else:
        if "Sitemap:" not in robots.text:
            fail("/robots.txt", "does not point at the sitemap")
        if re.search(r"^Disallow: /$", robots.text, re.M):
            fail("/robots.txt", "disallows the whole site")

    # --------------------------------------------------------------- 404
    missing = client.get("/no-such-page-here")
    if missing.status_code != 404:
        fail("/404", f"unknown page returned {missing.status_code}, not 404")
    elif "text/html" not in missing.headers.get("content-type", ""):
        fail("/404", "unknown page did not return the HTML error page")
    elif "noindex" not in (meta(missing.text, "robots") or ""):
        fail("/404", "the 404 page is indexable")

    api_missing = client.get("/api/v1/no-such-endpoint")
    if "application/json" not in api_missing.headers.get("content-type", ""):
        fail("/api", "a missing API endpoint returned HTML instead of JSON")

    # ------------------------------------------------------- redirects
    # One page must not be reachable at several URLs: the canonical tag says
    # which one counts, and these make the others stop existing.
    for url, filename in ROUTES.items():
        if url == "/":
            continue
        response = client.get(f"/{filename}", follow_redirects=False)
        if response.status_code != 301:
            fail(f"/{filename}", f"should 301 to {url}, got {response.status_code}")

        trailing = client.get(f"{url}/", follow_redirects=False)
        if trailing.status_code != 301:
            fail(f"{url}/", f"should 301 to {url}, got {trailing.status_code}")

    # --------------------------------------------------------- caching
    head = client.get("/")
    if "must-revalidate" not in head.headers.get("cache-control", ""):
        fail("/", "HTML is cacheable without revalidation; deploys will be invisible")
    asset = re.search(r'/assets/([^"]+\.js)', client.get("/app").text)
    if asset:
        response = client.get(f"/assets/{asset.group(1)}")
        if "immutable" not in response.headers.get("cache-control", ""):
            warn("/assets", "hashed assets are not marked immutable")

    # ---------------------------------------------------------- report
    for message in warnings:
        print(f"[warn] {message}")
    for message in failures:
        print(f"[FAIL] {message}")
    print(
        f"\n{len(ROUTES)} pages, {len(internal_links)} internal links checked · "
        f"{len(failures)} failure(s), {len(warnings)} warning(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
