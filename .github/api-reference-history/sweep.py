#!/usr/bin/env python3
"""Sweep historical API-reference page URLs against a deployed site."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


PAGE_URL = re.compile(
    r"^/(?:(?P<language>es|fr)/)?api-reference/"
    r"(?P<version>v\d{2}\.\d{2}\.\d{2})/(?P<slug>.+)$"
)
REDIRECTS = {301, 302, 303, 307, 308}
RETRYABLE = {429, 500, 502, 503}
MAX_HOPS = 3


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--parallel", type=int, default=6)
    args = parser.parse_args()
    if args.parallel < 1:
        parser.error("--parallel must be at least 1")
    return args


def expected_page(url: str, snapshots: set[str], old_only: dict) -> tuple[str, bool]:
    match = PAGE_URL.fullmatch(url)
    if match is None:
        raise ValueError(f"unrecognized historical page URL: {url}")
    if match.group("version") in snapshots:
        return url, True
    language = match.group("language") or "en"
    destination = old_only.get(match.group("slug"), {}).get(language)
    if destination:
        return destination, False
    locale = "" if language == "en" else f"/{language}"
    return f"{locale}/api-reference/{match.group('slug')}", False


def request_status(url: str) -> tuple[int, str | None]:
    for attempt in range(4):
        request = Request(url, headers={"User-Agent": "firma-docs-history-sweep/1"})
        try:
            with OPENER.open(request, timeout=30) as response:
                status = response.status
                location = response.headers.get("Location")
        except HTTPError as exc:
            status = exc.code
            location = exc.headers.get("Location")
        except URLError as exc:
            raise RuntimeError(f"request failed: {exc.reason}") from exc
        if status not in RETRYABLE or attempt == 3:
            return status, location
        time.sleep(0.5 * (2 ** attempt))
    raise AssertionError("retry loop did not return")


def normalized_path(url: str) -> str:
    path = urlparse(url).path
    normalized = "/" + "/".join(part for part in path.split("/") if part)
    return normalized if normalized != "" else "/"


def comparable_absolute_url(url: str) -> tuple[str, str, int | None, str]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        raise ValueError(f"URL is not absolute: {url}")
    port = parsed.port
    if port is None:
        port = {"http": 80, "https": 443}.get(scheme)
    return scheme, host, port, normalized_path(url)


def expected_absolute_url(base_url: str, expected: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", expected.lstrip("/"))


def sweep_one(base_url: str, url: str, expected: str, direct: bool) -> tuple[str, str | None]:
    current = urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    hops = 0
    while True:
        try:
            status, location = request_status(current)
        except RuntimeError as exc:
            return url, str(exc)
        if status in REDIRECTS:
            if direct:
                return url, f"snapshot redirected ({status}) to {location}"
            if location is None:
                return url, f"redirect {status} has no Location header"
            if hops >= MAX_HOPS:
                return url, f"exceeded {MAX_HOPS} redirect hops"
            current = urljoin(current, location)
            hops += 1
            continue
        if status != 200:
            return url, f"final status {status} after {hops} hops at {current}"
        expected_url = expected_absolute_url(base_url, expected)
        try:
            actual_comparable = comparable_absolute_url(current)
            expected_comparable = comparable_absolute_url(expected_url)
        except ValueError as exc:
            return url, str(exc)
        if actual_comparable != expected_comparable:
            return url, (
                f"wrong final page after {hops} hops: {current}, "
                f"expected {expected_url}"
            )
        return url, None


def main() -> int:
    args = parse_args()
    history = Path(__file__).resolve().parent
    try:
        inventory = json.loads((history / "urls.json").read_text())
        state = json.loads((history / "state.json").read_text())
    except Exception as exc:
        print(f"FAIL: cannot load release history: {exc}", file=sys.stderr)
        return 1

    snapshots = {state["current_version"], *state["dropdown_snapshots"]}
    jobs: list[tuple[str, str, bool]] = []
    failures: list[str] = []
    for entry in inventory.get("entries", []):
        if entry.get("kind") != "page":
            continue
        url = entry["url"]
        try:
            expected, direct = expected_page(url, snapshots, state["old_only_slugs"])
        except ValueError as exc:
            failures.append(str(exc))
            continue
        jobs.append((url, expected, direct))

    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(sweep_one, args.base_url, url, expected, direct): url
            for url, expected, direct in jobs
        }
        completed = 0
        for future in as_completed(futures):
            url, error = future.result()
            completed += 1
            if error:
                failures.append(f"{url}: {error}")
            if completed % 500 == 0:
                print(f"Checked {completed}/{len(jobs)} pages...", file=sys.stderr)

    if failures:
        print(f"FAIL ({len(failures)} of {len(jobs)} page URLs)")
        for failure in sorted(failures):
            print(failure)
        return 1
    print(f"PASS: {len(jobs)} historical page URLs reached their expected pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
