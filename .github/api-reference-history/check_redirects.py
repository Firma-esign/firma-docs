#!/usr/bin/env python3
"""Offline validator for the cumulative API-reference URL history."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


VERSION = re.compile(r"v\d{2}\.\d{2}\.\d{2}")
VERSION_PATH = re.compile(r"api-reference/v\d{2}\.\d{2}\.\d{2}/")
RAW_URL = re.compile(
    r"^https://raw\.githubusercontent\.com/Firma-esign/firma-docs/"
    r"(?P<sha>[0-9a-f]{40})/(?P<path>.+)$"
)
SNAPSHOTS = {"v01.40.04", "v01.40.02", "v01.40.01", "v01.40.00", "v01.39.01", "v01.39.00"}
NAVIGATION_VERSION_LABELS = [
    "v1.40.4 (latest)",
    "v1.40.2",
    "v1.40.1",
    "v1.40.0",
    "v1.39.1",
    "v1.39.0",
]
HISTORY_PATH = re.compile(
    r"^(?:(?:es|fr)/)?api-reference/v\d{2}\.\d{2}\.\d{2}/(?:.+\.mdx|openapi[^/]*\.json)$"
)
COMPATIBILITY_VERSIONS = ["v01.00.01", "v01.00.02"] + [f"v01.{minor:02d}.00" for minor in range(1, 10)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--docs-json", type=Path)
    parser.add_argument("--inventory", type=Path)
    return parser.parse_args()


def frontmatter(text: str, path: Path, errors: list[str]) -> str:
    if not text.startswith("---\n") or len(re.findall(r"^---$", text, re.MULTILINE)) != 2:
        errors.append(f"frontmatter: {path} does not have one parseable frontmatter block")
        return ""
    return text.split("\n---", 1)[0] + "\n"


def file_for_url(root: Path, url: str) -> Path | None:
    relative = url.lstrip("/")
    direct = root / relative
    if direct.is_file():
        return direct
    for suffix in (".mdx", ".md"):
        candidate = root / (relative + suffix)
        if candidate.is_file():
            return candidate
    return None


def match_rule(url: str, rules: list[dict]) -> dict | None:
    for rule in rules:
        if ":slug*" not in rule["source"] and rule["source"] == url:
            return rule
    for rule in rules:
        source = rule["source"]
        if ":slug*" not in source:
            continue
        prefix = source.removesuffix(":slug*")
        bare = prefix.removesuffix("/")
        if url == bare or url.startswith(prefix):
            slug = "" if url == bare else url[len(prefix):]
            resolved = dict(rule)
            resolved["destination"] = rule["destination"].replace(":slug*", slug)
            return resolved
    return None


def git_object_exists(git_root: Path, sha: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}:{path}"],
        cwd=git_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def git_tree_paths(git_root: Path, sha: str) -> set[str] | None:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", sha],
        cwd=git_root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return {path for path in result.stdout.splitlines() if HISTORY_PATH.fullmatch(path)}


def historical_url(path: str) -> str:
    return "/" + (path[:-4] if path.endswith(".mdx") else path)


def page_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from page_values(item)
    elif isinstance(value, dict):
        if "pages" in value:
            yield from page_values(value["pages"])


def path_to_url(root: Path, path: Path) -> str | None:
    relative = path.relative_to(root).as_posix()
    if path.suffix in (".mdx", ".md"):
        return "/" + relative.rsplit(".", 1)[0]
    if path.suffix == ".json":
        return "/" + relative
    return None


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    docs_path = (args.docs_json or root / "docs.json").resolve()
    inventory_path = (args.inventory or root / ".github/api-reference-history/urls.json").resolve()
    git_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=root,
        text=True, capture_output=True,
    )
    git_root = Path(git_root_result.stdout.strip()) if git_root_result.returncode == 0 else Path.cwd()
    errors: list[str] = []
    try:
        docs = json.loads(docs_path.read_text())
    except Exception as exc:
        print(f"FAIL\ndocs.json: {exc}")
        return 1
    try:
        inventory = json.loads(inventory_path.read_text())
    except Exception as exc:
        print(f"FAIL\ninventory: {exc}")
        return 1

    rules = docs.get("redirects", [])
    sources = [rule.get("source") for rule in rules]
    if len(sources) != len(set(sources)):
        errors.append("redirects: duplicate sources exist")
    wildcard_seen = False
    for index, rule in enumerate(rules):
        if set(rule) != {"source", "destination", "permanent"}:
            errors.append(f"redirects[{index}]: unexpected shape")
        if rule.get("permanent") is not True:
            errors.append(f"redirects[{index}]: permanent must be true")
        source = rule.get("source", "")
        if ":slug*" in source:
            wildcard_seen = True
        elif wildcard_seen:
            errors.append(f"redirects[{index}]: exact rule appears after the first wildcard rule")

    entries = inventory.get("entries", [])
    urls = [entry.get("url") for entry in entries]
    if urls != sorted(urls):
        errors.append("inventory: entries are not sorted by URL")
    if len(urls) != len(set(urls)):
        errors.append("inventory: duplicate URLs exist")

    generated_from = inventory.get("generated_from", [])
    expected_history: dict[str, dict] = {}
    trees: dict[str, set[str]] = {}
    for sha in generated_from:
        paths = git_tree_paths(git_root, sha)
        if paths is None:
            errors.append(f"inventory: origin commit is unavailable: {sha}")
            continue
        trees[sha] = paths
        for path in paths:
            expected_history[historical_url(path)] = {
                "kind": "page" if path.endswith(".mdx") else "spec",
                "origin_sha": sha,
                "path": path,
                "url": historical_url(path),
            }
    normal_entries = {entry["url"]: entry for entry in entries if entry.get("kind") != "compatibility"}
    for url in sorted(set(expected_history) - set(normal_entries)):
        errors.append(f"inventory: missing historical entry: {url}")
    for url in sorted(set(normal_entries) - set(expected_history)):
        errors.append(f"inventory: unexpected historical entry: {url}")
    for url in sorted(set(normal_entries) & set(expected_history)):
        if normal_entries[url] != expected_history[url]:
            errors.append(f"inventory: wrong origin metadata: {url}")

    compatibility_entries = {entry["url"]: entry for entry in entries if entry.get("kind") == "compatibility"}
    expected_compatibility = {}
    if generated_from:
        old_sha = generated_from[0]
        for version in COMPATIBILITY_VERSIONS:
            path = f"api-reference/{version}/openapi-{version}.json"
            url = f"/api-reference/v01.10.00/openapi-{version}.json"
            expected_compatibility[url] = {
                "kind": "compatibility",
                "origin_sha": old_sha,
                "path": path,
                "url": url,
            }
    if compatibility_entries != expected_compatibility:
        errors.append("inventory: compatibility entries do not match the 11 cached redirect destinations")
    for entry in compatibility_entries.values():
        if entry["origin_sha"] not in trees or entry["path"] not in trees[entry["origin_sha"]]:
            errors.append(f"inventory: compatibility origin missing: {entry['url']} -> {entry['origin_sha']}:{entry['path']}")

    for entry in entries:
        url = entry["url"]
        live = file_for_url(root, url)
        rule = match_rule(url, rules)
        if live is not None:
            if rule is not None:
                errors.append(f"historical URL: live source also redirects: {url} -> {rule['destination']}")
            continue
        if rule is None:
            errors.append(f"historical URL: no live file or redirect: {url}")
            continue
        destination = rule["destination"]
        if match_rule(destination, rules) is not None:
            errors.append(f"historical URL: redirect chain: {url} -> {destination}")
            continue
        raw = RAW_URL.match(destination)
        if raw:
            if (raw.group("sha"), raw.group("path")) != (entry["origin_sha"], entry["path"]):
                errors.append(
                    f"historical URL: raw destination mismatch: {url} -> {destination} "
                    f"(expected {entry['origin_sha']}:{entry['path']})"
                )
            if not git_object_exists(git_root, raw.group("sha"), raw.group("path")):
                errors.append(f"historical URL: raw destination missing: {url} -> {destination}")
        elif file_for_url(root, destination) is None:
            errors.append(f"historical URL: destination missing: {url} -> {destination}")

    live_urls: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        url = path_to_url(root, path)
        if url is not None:
            live_urls.append((url, path))
    for url, path in live_urls:
        rule = match_rule(url, rules)
        if rule is not None:
            errors.append(f"redirect source: live file is shadowed: {url} ({path.relative_to(root)})")

    for rule in rules:
        destination = rule["destination"]
        if RAW_URL.match(destination):
            continue
        probes = [destination]
        if ":slug*" in rule["source"]:
            probes = [
                destination.replace(":slug*", ""),
                destination.replace(":slug*", "redirect-probe"),
            ]
            empty_destination = probes[0]
            empty_path = root / empty_destination.lstrip("/")
            if file_for_url(root, empty_destination) is None and not empty_path.is_dir():
                errors.append(
                    f"redirect destination: empty wildcard destination missing: "
                    f"{rule['source']} -> {empty_destination}"
                )
        for probe in probes:
            chained = match_rule(probe, rules)
            if chained is not None:
                errors.append(
                    f"redirect destination: is also a source: {probe} matches {chained['source']}"
                )

    languages = docs.get("navigation", {}).get("languages", [])
    language_codes = [language.get("language") for language in languages]
    if language_codes != ["en", "es", "fr"]:
        errors.append(f"navigation: languages must be exactly en, es, fr in order: {language_codes}")
    for language in languages:
        code = language.get("language", "?")
        versions = language.get("versions", [])
        if not versions:
            errors.append(f"navigation: {code} has no versions")
            continue
        version_labels = [version.get("version") for version in versions]
        if version_labels != NAVIGATION_VERSION_LABELS:
            errors.append(
                f"navigation: {code} version labels must be exactly "
                f"{NAVIGATION_VERSION_LABELS}: {version_labels}"
            )
        for version_index, version in enumerate(versions):
            for tab in version.get("tabs", []):
                for page in page_values(tab.get("groups", [])):
                    if file_for_url(root, "/" + page.lstrip("/")) is None:
                        errors.append(f"navigation: missing page for {code} version {version_index}: {page}")
                    if version_index == 0 and VERSION_PATH.search(page):
                        errors.append(f"navigation: first {code} version is pinned: {page}")
                    if version_index > 0 and "api-reference/" in page and not VERSION_PATH.search(page):
                        errors.append(
                            f"navigation: stable API path outside first {code} version: {page}"
                        )

    actual_specs = sorted(path.relative_to(root).as_posix() for path in root.rglob("openapi*.json") if ".git" not in path.parts)
    configured_specs = docs.get("api", {}).get("openapi", [])
    if configured_specs != sorted(configured_specs):
        errors.append("api.openapi: paths are not sorted")
    missing_config = sorted(set(actual_specs) - set(configured_specs))
    stale_config = sorted(set(configured_specs) - set(actual_specs))
    for path in missing_config:
        errors.append(f"api.openapi: unlisted spec: {path}")
    for path in stale_config:
        errors.append(f"api.openapi: listed spec missing: {path}")

    for locale in ("", "es/", "fr/"):
        base = root / locale / "api-reference"
        for version in SNAPSHOTS:
            folder = base / version
            if not folder.is_dir():
                errors.append(f"snapshot: missing folder: {folder.relative_to(root)}")
                continue
            for stub in folder.rglob("*.mdx"):
                fm = frontmatter(stub.read_text(), stub.relative_to(root), errors)
                count = len(re.findall(r"^noindex:\s*true\s*$", fm, re.MULTILINE))
                if count != 1:
                    errors.append(f"snapshot: expected one noindex true, found {count}: {stub.relative_to(root)}")
        for stub in base.rglob("*.mdx"):
            relative = stub.relative_to(base)
            if any(VERSION.fullmatch(part) for part in relative.parts):
                continue
            fm = frontmatter(stub.read_text(), stub.relative_to(root), errors)
            count = len(re.findall(r"^noindex:\s*true\s*$", fm, re.MULTILINE))
            if count:
                errors.append(f"stable stub: contains noindex true: {stub.relative_to(root)}")

    for path in root.rglob("*.mdx"):
        relative = path.relative_to(root)
        if "api-reference" in relative.parts or path.name == "api-changelog.mdx":
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if VERSION_PATH.search(line):
                errors.append(f"guide: versioned API-reference path: {relative}:{line_number}")

    raw_in_text = re.compile(
        r"https://raw\.githubusercontent\.com/Firma-esign/firma-docs/[0-9a-f]{40}/"
        r"api-reference/v\d{2}\.\d{2}\.\d{2}/openapi[^\s)`>\"\]]+\.json"
    )
    relative_changelog_spec = re.compile(
        r"/api-reference/(?P<version>v\d{2}\.\d{2}\.\d{2})/"
        r"openapi-v\d{2}\.\d{2}\.\d{2}(?:\.(?:es|fr))?\.json"
    )
    for path in (root / "guides/api-changelog.mdx", root / "es/guides/api-changelog.mdx", root / "fr/guides/api-changelog.mdx"):
        if not path.is_file():
            errors.append(f"changelog: missing {path.relative_to(root)}")
            continue
        stripped = raw_in_text.sub("", path.read_text())
        for match in relative_changelog_spec.finditer(stripped):
            if match.group("version") not in SNAPSHOTS:
                errors.append(f"changelog: retired relative spec link: {path.relative_to(root)}: {match.group(0)}")

    if errors:
        print(f"FAIL ({len(errors)} offenders)")
        for error in errors:
            print(error)
        return 1
    print(
        f"PASS: {len(entries)} historical URLs, {len(rules)} redirects, "
        f"{len(actual_specs)} OpenAPI specs, navigation and noindex invariants valid"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
