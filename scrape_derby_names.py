from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import string
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup


DEFAULT_URLS = [
    "https://www.derbyrollcall.com/everyone",
    "https://rollerderbyroster.com/view-names/",
]

ROSTER_BASE_URL = "https://rollerderbyroster.com/view-names/"

LOGGER = logging.getLogger("derby_scraper")


def fetch_html(url: str, timeout: int = 30) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    return response.text


def configure_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def extract_names_from_dom(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    names: set[str] = set()

    # Primary strategy: scrape all links to profile pages and use visible link text.
    for anchor in soup.select('a[href*="/profile/"]'):
        text = anchor.get_text(" ", strip=True)
        if text:
            names.add(text)

    # Fallback strategy: inspect text-like elements in case profile links are absent.
    if not names:
        for node in soup.select("h1, h2, h3, h4, p, li, span, div"):
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            if len(text) > 60:
                continue
            if re.search(r"^[A-Za-z0-9 .,'!\-]+$", text):
                if "derby" not in text.lower() and "roll call" not in text.lower():
                    names.add(text)

    return names


def extract_names_from_embedded_json(html: str) -> set[str]:
    names: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script"):
        raw = script.string
        if not raw:
            continue
        raw_lower = raw.lower()
        if "name" not in raw_lower and "profile" not in raw_lower:
            continue

        # Attempt to decode JSON blobs from script tags.
        for candidate in re.findall(r"\{.*?\}|\[.*?\]", raw, flags=re.DOTALL):
            try:
                decoded = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue

            stack = [decoded]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    for key, value in item.items():
                        if key.lower() in {"name", "derby_name", "display_name"} and isinstance(value, str):
                            cleaned = value.strip()
                            if cleaned:
                                names.add(cleaned)
                        else:
                            stack.append(value)
                elif isinstance(item, list):
                    stack.extend(item)

    return names


def clean_names(names: set[str]) -> list[str]:
    by_key: dict[str, str] = {}
    for name in names:
        value = re.sub(r"\s+", " ", name).strip()
        if not value:
            continue
        if value.lower() in {"everyone", "search", "next", "previous"}:
            continue

        # Deduplicate case-insensitively while preserving a readable display value.
        key = value.casefold()
        if key not in by_key:
            by_key[key] = value
        else:
            # Prefer the shorter/canonical-looking variant if duplicates differ only by casing/spaces.
            existing = by_key[key]
            if (len(value), value.casefold(), value) < (len(existing), existing.casefold(), existing):
                by_key[key] = value

    return sorted(by_key.values(), key=lambda x: x.casefold())


def write_csv(names: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name"])
        for name in names:
            writer.writerow([name])


def expand_source_urls(urls: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()

    for url in urls:
        split = urlsplit(url)
        normalized = f"{split.scheme}://{split.netloc}{split.path}"

        if normalized.rstrip("/") == ROSTER_BASE_URL.rstrip("/"):
            qs = parse_qs(split.query)
            if "ini" in qs:
                candidates = [url]
            else:
                candidates = [f"{ROSTER_BASE_URL}?ini={letter}" for letter in string.ascii_uppercase]
        else:
            candidates = [url]

        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)

    return expanded


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape roller derby names to CSV")
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Source page URL. Repeat to provide multiple URLs.",
    )
    parser.add_argument("--output", default="data/derby_names.csv", help="CSV output path")
    parser.add_argument("--verbose", action="store_true", help="Enable progress logging")
    args = parser.parse_args()

    configure_logging(args.verbose)

    urls = args.urls if args.urls else DEFAULT_URLS
    expanded_urls = expand_source_urls(urls)
    LOGGER.info("Planned %d page(s) from %d source URL(s)", len(expanded_urls), len(urls))

    names: set[str] = set()
    for idx, url in enumerate(expanded_urls, start=1):
        LOGGER.info("Fetching page %d/%d: %s", idx, len(expanded_urls), url)
        html = fetch_html(url)
        discovered = extract_names_from_dom(html)
        method = "dom"
        if not discovered:
            discovered = extract_names_from_embedded_json(html)
            method = "embedded_json"
        LOGGER.info("Page %d yielded %d names via %s", idx, len(discovered), method)
        names.update(discovered)

    LOGGER.info("Collected %d raw names before cleaning", len(names))

    cleaned = clean_names(names)
    if not cleaned:
        raise RuntimeError("No derby names found. The site structure may have changed.")

    LOGGER.info("Retained %d names after dedupe/cleanup", len(cleaned))

    output_path = Path(args.output)
    write_csv(cleaned, output_path)
    print(f"Saved {len(cleaned)} names from {len(expanded_urls)} fetched page(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())