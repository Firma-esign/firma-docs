#!/usr/bin/env python3
"""Offline validator for the cumulative API-reference URL history."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin


VERSION = re.compile(r"v\d{2}\.\d{2}\.\d{2}")
VERSION_PATH = re.compile(r"api-reference/v\d{2}\.\d{2}\.\d{2}/")
RAW_URL = re.compile(
    r"^https://raw\.githubusercontent\.com/Firma-esign/firma-docs/"
    r"(?P<sha>[0-9a-f]{40})/(?P<path>.+)$"
)
HISTORY_PATH = re.compile(
    r"^(?:(?:es|fr)/)?api-reference/v\d{2}\.\d{2}\.\d{2}/(?:.+\.mdx|openapi[^/]*\.json)$"
)
COMPATIBILITY_VERSIONS = ["v01.00.01", "v01.00.02"] + [f"v01.{minor:02d}.00" for minor in range(1, 10)]
DOCS_HOSTED_SPEC = re.compile(
    r"^https://docs\.firma\.dev(?P<path>/(?:es/|fr/)?api-reference/"
    r"(?:v\d{2}\.\d{2}\.\d{2}/)?openapi[^/]*\.json)$"
)
LOCAL_SPEC = re.compile(
    r"^/(?:es/|fr/)?api-reference/"
    r"(?:(?P<version>v\d{2}\.\d{2}\.\d{2})/)?openapi[^/]*\.json$"
)
INLINE_LINK = re.compile(r"\]\(\s*<?(?P<target>[^\s)>]+)>?")
REFERENCE_LINK = re.compile(r"^\s*\[[^]]+\]:\s*<?(?P<target>[^\s>]+)>?")
HREF_LINK = re.compile(
    r"\bhref\s*=\s*[\"'](?P<target>[^\"']+)[\"']",
    re.IGNORECASE,
)
BARE_SPEC_URL = re.compile(
    r"https://(?:raw\.githubusercontent\.com|docs\.firma\.dev)/"
    r"[^\s<>\"'()\[\]]*openapi[^\s<>\"'()\[\]]*\.json",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--docs-json", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--state", type=Path)
    return parser.parse_args()


def version_label(version: str, latest: bool = False) -> str:
    major, minor, patch = (int(part) for part in version[1:].split("."))
    label = f"v{major}.{minor}.{patch}"
    return f"{label} (latest)" if latest else label


def state_values(state: dict) -> tuple[set[str], list[str], dict[str, str]]:
    current = state["current_version"]
    dropdown = state["dropdown_snapshots"]
    snapshots = {current, *dropdown}
    labels = [version_label(current, latest=True)] + [
        version_label(version) for version in dropdown
    ]
    old_only: dict[str, str] = {}
    for slug, destinations in state["old_only_slugs"].items():
        for language, destination in destinations.items():
            locale = "" if language == "en" else f"/{language}"
            old_only[f"{locale}/api-reference/{slug}"] = destination
    return snapshots, labels, old_only


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


def normalized_path(path: str) -> str:
    normalized = "/" + "/".join(part for part in path.split("/") if part)
    return normalized if normalized != "" else "/"


def terminal_wildcard_prefix(pattern: str) -> str | None:
    if pattern.count(":slug*") != 1 or not pattern.endswith("/:slug*"):
        return None
    return normalized_path(pattern.removesuffix("/:slug*"))


def path_is_within(path: str, prefix: str) -> bool:
    path = normalized_path(path)
    prefix = normalized_path(prefix)
    return path == prefix or prefix == "/" or path.startswith(prefix + "/")


def self_matching_wildcard(rule: dict) -> bool:
    source = rule.get("source", "")
    destination = rule.get("destination", "")
    if not isinstance(source, str) or not isinstance(destination, str):
        return False
    source_prefix = terminal_wildcard_prefix(source)
    if source_prefix is None:
        return False
    destination_prefix = terminal_wildcard_prefix(destination)
    if destination_prefix is None:
        return ":slug*" not in destination and path_is_within(destination, source_prefix)
    return (
        path_is_within(source_prefix, destination_prefix)
        or path_is_within(destination_prefix, source_prefix)
    )


def wildcard_destination_base_exists(root: Path, destination: str) -> bool:
    prefix = terminal_wildcard_prefix(destination)
    if prefix is None:
        return page_for_url(root, destination) is not None
    return (root / prefix.lstrip("/")).is_dir() or page_for_url(root, prefix) is not None


def spec_targets(line: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for pattern in (INLINE_LINK, REFERENCE_LINK, HREF_LINK, BARE_SPEC_URL):
        for match in pattern.finditer(line):
            target = match.groupdict().get("target") or match.group(0)
            if (
                "openapi" in target.lower()
                and target.lower().endswith(".json")
                and target not in seen
            ):
                seen.add(target)
                targets.append(target)
    return targets


def match_rule(url: str, rules: list[dict]) -> dict | None:
    if url.endswith(".json"):
        return None
    for rule in rules:
        source = rule["source"]
        if ":slug*" not in source and source == url:
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


def page_for_url(root: Path, url: str) -> Path | None:
    path = file_for_url(root, url)
    if path is not None and path.suffix in (".mdx", ".md"):
        return path
    return None


def exact_redirect_error(root: Path, source: str, rules: list[dict]) -> str | None:
    current = source
    hops = 0
    while True:
        rule = match_rule(current, rules)
        if rule is None:
            if page_for_url(root, current) is None:
                return f"missing destination after {hops} hops: {source} -> {current}"
            return None
        if hops == 1 and ":slug*" in rule["source"]:
            return (
                f"second hop must be exact: {source} -> {current} "
                f"matches {rule['source']}"
            )
        if hops >= 2:
            return (
                f"redirect chain exceeds two hops: "
                f"{source} -> {current} -> {rule['destination']}"
            )
        hops += 1
        current = rule["destination"]
        if current.startswith(("https://", "http://")):
            return f"external destination is not used: {source} -> {current}"


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
    state_path = (args.state or root / ".github/api-reference-history/state.json").resolve()
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
    try:
        state = json.loads(state_path.read_text())
        snapshots, navigation_version_labels, old_only_destinations = state_values(state)
    except Exception as exc:
        print(f"FAIL\nstate: {exc}")
        return 1

    rules = docs.get("redirects", [])
    sources = [rule.get("source") for rule in rules]
    if len(sources) != len(set(sources)):
        errors.append("redirects: duplicate sources exist")
    wildcard_seen = False
    unmaterialized_wildcards: list[tuple[int, str, str]] = []
    for index, rule in enumerate(rules):
        if set(rule) != {"source", "destination", "permanent"}:
            errors.append(f"redirects[{index}]: unexpected shape")
        if rule.get("permanent") is not True:
            errors.append(f"redirects[{index}]: permanent must be true")
        source = rule.get("source", "")
        destination = rule.get("destination", "")
        if source.endswith(".json"):
            errors.append(
                f"redirects[{index}]: Mintlify never redirects .json paths: {source}"
            )
        if ":slug*" in source:
            wildcard_seen = True
            source_prefix = terminal_wildcard_prefix(source)
            if source_prefix is None:
                errors.append(
                    f"redirects[{index}]: wildcard source must contain exactly one "
                    f"terminal /:slug*: {source}"
                )
            if ":slug*" in destination and terminal_wildcard_prefix(destination) is None:
                errors.append(
                    f"redirects[{index}]: wildcard destination must contain exactly one "
                    f"terminal /:slug*: {destination}"
                )
            if source_prefix is not None and self_matching_wildcard(rule):
                errors.append(
                    f"redirects[{index}]: self-matching wildcard, Mintlify drops it: "
                    f"{source} -> {destination}"
                )
            elif (
                source_prefix is not None
                and not wildcard_destination_base_exists(root, destination)
            ):
                destination_base = terminal_wildcard_prefix(destination) or destination
                unmaterialized_wildcards.append((index, source_prefix, destination_base))
        elif wildcard_seen:
            errors.append(f"redirects[{index}]: exact rule appears after the first wildcard rule")
        if ":slug*" not in source and ":slug*" in destination:
            if terminal_wildcard_prefix(destination) is None:
                errors.append(
                    f"redirects[{index}]: wildcard destination must contain exactly one "
                    f"terminal /:slug*: {destination}"
                )
            errors.append(
                f"redirects[{index}]: exact source cannot supply a wildcard destination: "
                f"{source} -> {destination}"
            )
    mintlify_rules = [
        rule for rule in rules
        if isinstance(rule.get("source"), str)
        and isinstance(rule.get("destination"), str)
        and not rule["source"].endswith(".json")
        and (
            ":slug*" not in rule["source"]
            or terminal_wildcard_prefix(rule["source"]) is not None
        )
        and (
            ":slug*" not in rule["destination"]
            or terminal_wildcard_prefix(rule["destination"]) is not None
        )
        and not (
            ":slug*" not in rule["source"]
            and ":slug*" in rule["destination"]
        )
        and not self_matching_wildcard(rule)
    ]
    for rule in mintlify_rules:
        if ":slug*" in rule["source"]:
            continue
        expected_old_only = old_only_destinations.get(rule["source"])
        if expected_old_only is not None and rule["destination"] != expected_old_only:
            errors.append(
                f"old-only redirect: {rule['source']} must lead to "
                f"{expected_old_only}, got {rule['destination']}"
            )
        error = exact_redirect_error(root, rule["source"], mintlify_rules)
        if error is not None:
            errors.append(f"exact redirect: {error}")

    entries = inventory.get("entries", [])
    urls = [entry.get("url") for entry in entries]
    if urls != sorted(urls):
        errors.append("inventory: entries are not sorted by URL")
    if len(urls) != len(set(urls)):
        errors.append("inventory: duplicate URLs exist")

    generated_from = inventory.get("generated_from", [])
    retired_from = inventory.get("retired_from", {})
    expected_history: dict[str, dict] = {}
    path_origins: dict[str, set[str]] = {}
    trees: dict[str, set[str]] = {}
    for sha in generated_from:
        paths = git_tree_paths(git_root, sha)
        if paths is None:
            errors.append(f"inventory: origin commit is unavailable: {sha}")
            continue
        trees[sha] = paths
        selected_paths = paths
        if sha in retired_from:
            retired_versions = set(retired_from[sha])
            selected_paths = {
                path for path in paths
                if any(f"/{version}/" in f"/{path}" for version in retired_versions)
            }
        for path in selected_paths:
            path_origins.setdefault(path, set()).add(sha)
            expected_history[historical_url(path)] = {
                "kind": "page" if path.endswith(".mdx") else "spec",
                "path": path,
                "url": historical_url(path),
            }
    normal_entries = {entry["url"]: entry for entry in entries if entry.get("kind") != "compatibility"}
    for url in sorted(set(expected_history) - set(normal_entries)):
        errors.append(f"inventory: missing historical entry: {url}")
    for url in sorted(set(normal_entries) - set(expected_history)):
        errors.append(f"inventory: unexpected historical entry: {url}")
    for url in sorted(set(normal_entries) & set(expected_history)):
        entry_without_origin = {
            key: value for key, value in normal_entries[url].items()
            if key != "origin_sha"
        }
        if entry_without_origin != expected_history[url]:
            errors.append(f"inventory: wrong origin metadata: {url}")
            continue
        path = normal_entries[url]["path"]
        if normal_entries[url].get("origin_sha") not in path_origins.get(path, set()):
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

    page_entries = [entry for entry in entries if entry.get("kind") == "page"]
    hop_histogram: Counter[int] = Counter()
    resolved_page_urls: set[str] = set()
    for entry in page_entries:
        url = entry["url"]
        current = url
        hops = 0
        while True:
            rule = match_rule(current, mintlify_rules)
            if rule is not None:
                if hops == 1 and ":slug*" in rule["source"]:
                    errors.append(
                        f"historical page: second hop must be exact, wildcard matched: "
                        f"{url} -> {current} matches {rule['source']}"
                    )
                    break
                if hops >= 2:
                    errors.append(
                        f"historical page: redirect chain exceeds two hops: "
                        f"{url} -> {current} -> {rule['destination']}"
                    )
                    break
                hops += 1
                current = rule["destination"]
                continue
            if page_for_url(root, current) is None:
                errors.append(
                    f"historical page: missing destination after {hops} hops: "
                    f"{url} -> {current}"
                )
                break
            hop_histogram[hops] += 1
            resolved_page_urls.add(url)
            break

    inventory_urls = set(urls)
    informational_wildcards: list[tuple[int, str, str]] = []
    for index, source_prefix, destination_base in unmaterialized_wildcards:
        unresolved_pages = [
            entry["url"]
            for entry in page_entries
            if entry["url"] != source_prefix
            and path_is_within(entry["url"], source_prefix)
            and entry["url"] not in resolved_page_urls
        ]
        if unresolved_pages:
            errors.append(
                f"redirects[{index}]: wildcard destination base is missing and "
                f"{len(unresolved_pages)} inventory pages do not resolve: "
                f"{source_prefix}/:slug* -> {destination_base}"
            )
        elif source_prefix in inventory_urls:
            errors.append(
                f"redirects[{index}]: wildcard destination base is missing and "
                f"the bare source base is an inventory URL: "
                f"{source_prefix} -> {destination_base}"
            )
        else:
            informational_wildcards.append((index, source_prefix, destination_base))

    live_urls: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        url = path_to_url(root, path)
        if url is not None:
            live_urls.append((url, path))
    for url, path in live_urls:
        rule = match_rule(url, mintlify_rules)
        if rule is not None:
            errors.append(f"redirect source: live file is shadowed: {url} ({path.relative_to(root)})")

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
        if version_labels != navigation_version_labels:
            errors.append(
                f"navigation: {code} version labels must be exactly "
                f"{navigation_version_labels}: {version_labels}"
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
        for version in snapshots:
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

    spec_inventory_objects = {
        (entry["origin_sha"], entry["path"])
        for entry in entries if entry.get("kind") == "spec"
    }
    stable_spec_targets = {
        "/" + path
        for path in configured_specs
        if not any(VERSION.fullmatch(part) for part in Path(path).parts)
    }
    checked_git_objects: dict[tuple[str, str], bool] = {}
    changelog_paths = (
        root / "guides/api-changelog.mdx",
        root / "es/guides/api-changelog.mdx",
        root / "fr/guides/api-changelog.mdx",
    )
    for path in changelog_paths:
        if not path.is_file():
            errors.append(f"changelog: missing {path.relative_to(root)}")
    guide_paths = sorted(
        path for path in root.rglob("*.mdx")
        if "guides" in path.relative_to(root).parts
    )
    for path in guide_paths:
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            for target in spec_targets(line):
                raw = RAW_URL.fullmatch(target)
                if raw is not None:
                    git_object = (raw.group("sha"), raw.group("path"))
                    if git_object not in spec_inventory_objects:
                        errors.append(
                            f"guide spec: raw URL does not match inventory: "
                            f"{path.relative_to(root)}:{line_number}: {target}"
                        )
                        continue
                    if git_object not in checked_git_objects:
                        checked_git_objects[git_object] = git_object_exists(git_root, *git_object)
                    exists = checked_git_objects[git_object]
                    if not exists:
                        errors.append(
                            f"guide spec: raw object missing: "
                            f"{path.relative_to(root)}:{line_number}: {target}"
                        )
                    continue
                hosted = DOCS_HOSTED_SPEC.fullmatch(target)
                if hosted is not None:
                    local_target = hosted.group("path")
                elif target.startswith("/"):
                    local_target = target
                else:
                    guide_url = "/" + path.relative_to(root).as_posix()
                    local_target = urljoin(guide_url, target)
                local = LOCAL_SPEC.fullmatch(local_target)
                if local is None:
                    errors.append(
                        f"guide spec: target is not an inventory raw URL, stable spec, "
                        f"or snapshot file: "
                        f"{path.relative_to(root)}:{line_number}: {target}"
                    )
                    continue
                is_stable = local_target in stable_spec_targets
                is_snapshot = local.group("version") in snapshots
                if not is_stable and not is_snapshot:
                    errors.append(
                        f"guide spec: docs-hosted target is retired or unknown: "
                        f"{path.relative_to(root)}:{line_number}: {target}"
                    )
                    continue
                spec_file = root / local_target.lstrip("/")
                if not spec_file.is_file():
                    errors.append(
                        f"guide spec: local spec file missing: "
                        f"{path.relative_to(root)}:{line_number}: {target}"
                    )

    if informational_wildcards:
        destination_bases = sorted({item[2] for item in informational_wildcards})
        print(
            f"INFO: {len(informational_wildcards)} wildcard redirects use "
            f"non-materialized destination bases: {', '.join(destination_bases)}"
        )
    if errors:
        print(f"FAIL ({len(errors)} offenders)")
        for error in errors:
            print(error)
        return 1
    print(
        f"PASS: {len(page_entries)} historical pages resolve "
        f"(hops: 0={hop_histogram[0]}, 1={hop_histogram[1]}, 2={hop_histogram[2]}), "
        f"{len(entries) - len(page_entries)} spec URLs 404 by design, {len(rules)} redirects, "
        f"{len(actual_specs)} OpenAPI specs, Mintlify exact-first redirects, navigation and noindex invariants valid"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
