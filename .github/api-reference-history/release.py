#!/usr/bin/env python3
"""Prepare a stable-reference API documentation release."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from release_navigation import (
    api_tab_index,
    expected_navigation_pages,
    navigation_api_pages,
    snapshot_api_tab,
)


LANGUAGES = ("en", "es", "fr")
VERSION = re.compile(r"v\d{2}\.\d{2}\.\d{2}$")
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
OPENAPI_LINE = re.compile(
    r"^openapi:\s+\S+\s+(get|put|post|delete|options|head|patch|trace)\s+(\S+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--spec", action="append", default=[], metavar="LANG=PATH")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, text=True, capture_output=True)


def version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version[1:].split("."))


def version_label(version: str, latest: bool = False) -> str:
    label = "v" + ".".join(str(part) for part in version_tuple(version))
    return f"{label} (latest)" if latest else label


def locale_prefix(language: str) -> str:
    return "" if language == "en" else f"{language}/"


def api_base(root: Path, language: str) -> Path:
    return root / locale_prefix(language) / "api-reference"


def stable_stubs(root: Path, language: str) -> dict[str, Path]:
    base = api_base(root, language)
    result: dict[str, Path] = {}
    for path in base.rglob("*.mdx"):
        relative = path.relative_to(base)
        if any(VERSION.fullmatch(part) for part in relative.parts):
            continue
        result[relative.with_suffix("").as_posix()] = path
    return result


def snapshot_stubs(root: Path, language: str, version: str) -> dict[str, Path]:
    base = api_base(root, language) / version
    if not base.is_dir():
        return {}
    return {
        path.relative_to(base).with_suffix("").as_posix(): path
        for path in base.rglob("*.mdx")
    }


def stub_operation(path: Path) -> tuple[str, str] | None:
    matches = OPENAPI_LINE.findall(path.read_text())
    if len(matches) != 1:
        return None
    method, operation_path = matches[0]
    return method.lower(), operation_path


def spec_operations(spec: dict) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for operation_path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method.lower() in METHODS:
                operations.add((method.lower(), operation_path))
    return operations


def snapshot_stub_text(text: str, spec_url: str) -> str:
    lines = text.splitlines()
    lines.insert(1, "noindex: true")
    replacements = 0
    for index, line in enumerate(lines):
        if line.startswith("openapi:"):
            match = OPENAPI_LINE.fullmatch(line)
            if match is None:
                raise ValueError(f"unparseable openapi line: {line}")
            lines[index] = f"openapi: {spec_url} {match.group(1).lower()} {match.group(2)}"
            replacements += 1
    if replacements != 1 or not lines or lines[-1] != "---":
        raise ValueError("stub must contain one openapi line and end with ---")
    return "\n".join(lines)


def inventory_entry(path: str, sha: str) -> dict[str, str]:
    url = "/" + (path[:-4] if path.endswith(".mdx") else path)
    return {
        "kind": "page" if path.endswith(".mdx") else "spec",
        "origin_sha": sha,
        "path": path,
        "url": url,
    }


def dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def fail(errors: list[str]) -> int:
    print(f"PRECONDITION FAILED ({len(errors)} problems)", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 2


def restore_tree(
    root: Path,
    tracked_paths: list[str],
    created_paths: list[Path],
) -> list[str]:
    errors: list[str] = []
    if tracked_paths:
        restored = run(["git", "checkout", "HEAD", "--", *tracked_paths], root)
        if restored.returncode != 0:
            errors.append(restored.stderr.strip() or "git checkout failed")
    for path in created_paths:
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except Exception as exc:
            errors.append(f"cannot remove created file {path.relative_to(root)}: {exc}")
    created_directories = sorted(
        {
            parent
            for path in created_paths
            for parent in path.parents
            if parent != root and root in parent.parents
        },
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in created_directories:
        try:
            directory.rmdir()
        except OSError:
            pass
    return errors


def release_main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[2]
    history = root / ".github/api-reference-history"
    errors: list[str] = []

    spec_paths: dict[str, Path] = {}
    for value in args.spec:
        if "=" not in value:
            errors.append(f"--spec must be LANG=PATH: {value}")
            continue
        language, raw_path = value.split("=", 1)
        if language not in LANGUAGES:
            errors.append(f"unsupported spec language: {language}")
        elif language in spec_paths:
            errors.append(f"duplicate spec language: {language}")
        else:
            spec_paths[language] = Path(raw_path).expanduser().resolve()
    for language in LANGUAGES:
        if language not in spec_paths:
            errors.append(f"missing --spec {language}=PATH")

    status = run(["git", "status", "--porcelain=v1"], root)
    if status.returncode != 0:
        errors.append(f"cannot inspect worktree: {status.stderr.strip()}")
    elif status.stdout:
        errors.append("worktree is not clean")

    state = None
    docs = None
    inventory = None
    for name, path in (
        ("state", history / "state.json"),
        ("docs.json", root / "docs.json"),
        ("inventory", history / "urls.json"),
    ):
        try:
            value = json.loads(path.read_text())
        except Exception as exc:
            errors.append(f"{name} does not parse: {exc}")
            continue
        if name == "state":
            state = value
        elif name == "docs.json":
            docs = value
        else:
            inventory = value

    pre_release_docs = None
    parent = run(["git", "rev-parse", "--verify", "HEAD^"], root)
    if parent.returncode == 0:
        previous_docs = run(["git", "show", "HEAD^:docs.json"], root)
        if previous_docs.returncode != 0:
            errors.append(
                "cannot read pre-release docs.json from HEAD^: "
                + (previous_docs.stderr.strip() or "git show failed")
            )
        else:
            try:
                pre_release_docs = json.loads(previous_docs.stdout)
            except Exception as exc:
                errors.append(f"pre-release docs.json from HEAD^ does not parse: {exc}")

    new_version = args.version
    if VERSION.fullmatch(new_version) is None:
        errors.append("--version must have the form vNN.NN.NN")
    current_version = state.get("current_version") if isinstance(state, dict) else None
    if VERSION.fullmatch(str(current_version)) is None:
        errors.append("state current_version is invalid")
    elif VERSION.fullmatch(new_version) and version_tuple(new_version) <= version_tuple(current_version):
        errors.append(f"new version {new_version} is not greater than {current_version}")

    specs: dict[str, dict] = {}
    expected_info_version = new_version[1:] if VERSION.fullmatch(new_version) else None
    for language, path in spec_paths.items():
        try:
            value = json.loads(path.read_text())
        except Exception as exc:
            errors.append(f"{language} spec does not parse: {path}: {exc}")
            continue
        specs[language] = value
        actual = value.get("info", {}).get("version") if isinstance(value, dict) else None
        if expected_info_version is not None and actual != expected_info_version:
            errors.append(
                f"{language} spec info.version is {actual!r}, expected {expected_info_version!r}"
            )

    checker = run([sys.executable, str(history / "check_redirects.py"), "--root", str(root)], root)
    pre_checker_error = None
    if checker.returncode != 0:
        detail = checker.stdout.strip() or checker.stderr.strip()
        pre_checker_error = f"redirect checker does not pass before release:\n{detail}"

    stable: dict[str, dict[str, Path]] = {
        language: stable_stubs(root, language) for language in LANGUAGES
    }
    english_operations: dict[tuple[str, str], list[str]] = defaultdict(list)
    for slug, path in stable["en"].items():
        operation = stub_operation(path)
        if operation is None:
            errors.append(f"stable English stub has an invalid openapi line: {path.relative_to(root)}")
        else:
            english_operations[operation].append(slug)
    if "en" in specs:
        new_operations = spec_operations(specs["en"])
        for operation in sorted(new_operations):
            slugs = english_operations.get(operation, [])
            if len(slugs) == 0:
                errors.append(f"new English operation has no stable stub: {operation[0]} {operation[1]}")
            elif len(slugs) > 1:
                errors.append(
                    f"new English operation has {len(slugs)} stable stubs: "
                    f"{operation[0]} {operation[1]} ({', '.join(sorted(slugs))})"
                )
        for operation, slugs in sorted(english_operations.items()):
            if operation not in new_operations:
                for slug in sorted(slugs):
                    errors.append(
                        f"stable English stub points at an operation absent from the new spec: "
                        f"{slug} -> {operation[0]} {operation[1]}"
                    )

    english_slugs = set(stable["en"])
    for language in ("es", "fr"):
        slugs = set(stable[language])
        for slug in sorted(english_slugs - slugs):
            errors.append(f"{language} stable stubs are missing English slug: {slug}")
        for slug in sorted(slugs - english_slugs):
            errors.append(f"{language} stable stubs contain an extra slug: {slug}")

    language_blocks: dict[str, dict] = {}
    if isinstance(docs, dict):
        language_blocks = {
            block.get("language"): block
            for block in docs.get("navigation", {}).get("languages", [])
        }
        for language in LANGUAGES:
            block = language_blocks.get(language)
            if not block or not block.get("versions"):
                errors.append(f"navigation has no first version for {language}")
                continue
            actual_pages = navigation_api_pages(block["versions"][0], language)
            expected_pages = expected_navigation_pages(set(stable[language]), language)
            if Counter(actual_pages) != Counter(expected_pages):
                for page in sorted((Counter(expected_pages) - Counter(actual_pages)).elements()):
                    errors.append(f"{language} first-entry API tab is missing: {page}")
                for page in sorted((Counter(actual_pages) - Counter(expected_pages)).elements()):
                    errors.append(f"{language} first-entry API tab has an extra page: {page}")

    keep_older = state.get("keep_older") if isinstance(state, dict) else None
    dropdown = state.get("dropdown_snapshots") if isinstance(state, dict) else None
    if keep_older != 5:
        errors.append(f"state keep_older must be 5, got {keep_older!r}")
    if not isinstance(dropdown, list) or len(dropdown) != keep_older:
        errors.append("state dropdown_snapshots must contain keep_older versions")
        dropdown = []
    retired_version = dropdown[-1] if dropdown else None
    new_dropdown = ([current_version] + dropdown[: keep_older - 1]) if retired_version else []

    if current_version and VERSION.fullmatch(str(current_version)):
        for language in LANGUAGES:
            if not (api_base(root, language) / current_version).is_dir():
                errors.append(f"current snapshot folder is missing for {language}: {current_version}")
    if VERSION.fullmatch(new_version):
        for language in LANGUAGES:
            if (api_base(root, language) / new_version).exists():
                errors.append(f"new snapshot folder already exists for {language}: {new_version}")

    retired: dict[str, dict[str, Path]] = {}
    old_only_rules: list[dict] = []
    wildcard_rules: list[dict] = []
    prepared_removal = False
    if retired_version:
        old_only_map = state.get("old_only_slugs", {})
        existing_rules = {
            rule.get("source"): rule for rule in docs.get("redirects", [])
        } if isinstance(docs, dict) else {}
        for language in LANGUAGES:
            retired[language] = snapshot_stubs(root, language, retired_version)
            if not retired[language]:
                errors.append(f"retired snapshot folder has no stubs for {language}: {retired_version}")
                continue
            missing_slugs = set(retired[language]) - set(stable[language])
            prepared_removal = prepared_removal or bool(missing_slugs)
            for slug in sorted(missing_slugs):
                destination = old_only_map.get(slug, {}).get(language)
                if not destination:
                    errors.append(
                        f"retired {language} slug is missing from state old_only_slugs: {slug}"
                    )
                    continue
                locale = "" if language == "en" else f"/{language}"
                source = f"{locale}/api-reference/{slug}"
                rule = {"source": source, "destination": destination, "permanent": True}
                existing = existing_rules.get(source)
                if existing is not None and existing != rule:
                    errors.append(f"conflicting old-only redirect already exists: {source}")
                elif existing is None:
                    old_only_rules.append(rule)
            locale = "" if language == "en" else f"/{language}"
            for group in sorted({slug.split("/", 1)[0] for slug in retired[language]}):
                source = f"{locale}/api-reference/{retired_version}/{group}/:slug*"
                destination = f"{locale}/api-reference/{group}/:slug*"
                rule = {"source": source, "destination": destination, "permanent": True}
                existing = existing_rules.get(source)
                if existing is not None and existing != rule:
                    errors.append(f"conflicting retirement wildcard already exists: {source}")
                elif existing is None:
                    wildcard_rules.append(rule)

    if pre_checker_error is not None and not prepared_removal:
        errors.append(pre_checker_error)

    head_result = run(["git", "rev-parse", "HEAD"], root)
    head_sha = head_result.stdout.strip()
    if head_result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        errors.append("cannot resolve the current HEAD sha")

    changelog_changes: dict[Path, str] = {}
    if retired_version and head_sha:
        suffixes = {"en": "", "es": ".es", "fr": ".fr"}
        for language in LANGUAGES:
            changelog = root / locale_prefix(language) / "guides/api-changelog.mdx"
            filename = f"openapi-{retired_version}{suffixes[language]}.json"
            old_target = f"/api-reference/{retired_version}/{filename}"
            raw_target = (
                "https://raw.githubusercontent.com/Firma-esign/firma-docs/"
                f"{head_sha}/api-reference/{retired_version}/{filename}"
            )
            try:
                text = changelog.read_text()
            except Exception as exc:
                errors.append(f"cannot read {changelog.relative_to(root)}: {exc}")
                continue
            if old_target not in text:
                errors.append(
                    f"{language} changelog does not contain the retiring spec link: {old_target}"
                )
            else:
                changelog_changes[changelog] = text.replace(old_target, raw_target)

    if errors:
        return fail(errors)

    assert state is not None and docs is not None and inventory is not None
    assert retired_version is not None and current_version is not None

    planned_labels = [version_label(new_version, latest=True)] + [
        version_label(version) for version in new_dropdown
    ]
    retired_paths: list[str] = []
    for language in LANGUAGES:
        for path in (api_base(root, language) / retired_version).rglob("*"):
            if path.is_file():
                retired_paths.append(path.relative_to(root).as_posix())

    planned_docs = copy.deepcopy(docs)
    planned_blocks = {
        block["language"]: block
        for block in planned_docs["navigation"]["languages"]
    }
    pre_release_blocks = {
        block.get("language"): block
        for block in pre_release_docs.get("navigation", {}).get("languages", [])
    } if isinstance(pre_release_docs, dict) else {}
    for language in LANGUAGES:
        versions = planned_blocks[language]["versions"]
        latest = copy.deepcopy(versions[0])
        latest["version"] = version_label(new_version, latest=True)
        previous = copy.deepcopy(versions[0])
        previous["version"] = version_label(current_version)
        previous_api_index = api_tab_index(previous["tabs"], language)
        previous["tabs"][previous_api_index] = snapshot_api_tab(
            versions,
            language,
            current_version,
            set(snapshot_stubs(root, language, current_version)),
            (
                pre_release_blocks[language]["versions"][0]
                if pre_release_blocks.get(language, {}).get("versions")
                else None
            ),
        )
        planned_blocks[language]["versions"] = [latest, previous] + copy.deepcopy(
            versions[1:keep_older]
        )

    for language in LANGUAGES:
        versions = planned_blocks[language]["versions"]
        navigation_targets = [None, *new_dropdown]
        if len(versions) != len(navigation_targets):
            raise AssertionError(
                f"{language} planned navigation count does not match release state"
            )
        for index, (entry, version) in enumerate(zip(versions, navigation_targets)):
            if index == 0:
                expected_pages = expected_navigation_pages(set(stable[language]), language)
            else:
                expected_pages = [
                    f"{locale_prefix(language)}api-reference/{version}/{slug}"
                    for slug in sorted(snapshot_stubs(root, language, version))
                ]
            actual_pages = navigation_api_pages(entry, language)
            if Counter(actual_pages) != Counter(expected_pages):
                missing = sorted((Counter(expected_pages) - Counter(actual_pages)).elements())
                extra = sorted((Counter(actual_pages) - Counter(expected_pages)).elements())
                raise AssertionError(
                    f"{language} dropdown entry {index} does not exactly match "
                    f"its snapshot stubs; missing={missing}, extra={extra}"
                )

    exact_rules = [rule for rule in planned_docs["redirects"] if ":slug*" not in rule["source"]]
    wild_rules = [rule for rule in planned_docs["redirects"] if ":slug*" in rule["source"]]
    planned_docs["redirects"] = exact_rules + sorted(
        old_only_rules, key=lambda rule: rule["source"]
    ) + wild_rules + sorted(wildcard_rules, key=lambda rule: rule["source"])

    current_specs = {
        path.relative_to(root).as_posix()
        for path in root.rglob("openapi*.json")
        if ".git" not in path.parts
    }
    removed_prefixes = {
        (api_base(root, language) / retired_version).relative_to(root).as_posix() + "/"
        for language in LANGUAGES
    }
    planned_specs = {
        path for path in current_specs
        if not any(path.startswith(prefix) for prefix in removed_prefixes)
    }
    for language in LANGUAGES:
        suffix = "" if language == "en" else f".{language}"
        planned_specs.add(f"api-reference/{new_version}/openapi-{new_version}{suffix}.json")
    planned_docs["api"]["openapi"] = sorted(planned_specs)

    planned_state = copy.deepcopy(state)
    planned_state["current_version"] = new_version
    planned_state["dropdown_snapshots"] = new_dropdown
    for language in LANGUAGES:
        retired_versions = planned_state["retired_versions"][language]
        if retired_version not in retired_versions:
            retired_versions.append(retired_version)

    planned_inventory = copy.deepcopy(inventory)
    if head_sha not in planned_inventory["generated_from"]:
        planned_inventory["generated_from"].append(head_sha)
    retired_from = planned_inventory.setdefault("retired_from", {})
    retired_from.setdefault(head_sha, [])
    if retired_version not in retired_from[head_sha]:
        retired_from[head_sha].append(retired_version)
    entries = {entry["url"]: entry for entry in planned_inventory["entries"]}
    for path in retired_paths:
        entry = inventory_entry(path, head_sha)
        entries[entry["url"]] = entry
    planned_inventory["entries"] = [entries[url] for url in sorted(entries)]

    planned_writes: dict[Path, bytes] = {}
    stable_spec_names = {
        "en": "openapi.json",
        "es": "openapi.es.json",
        "fr": "openapi.fr.json",
    }
    for language in LANGUAGES:
        spec_bytes = spec_paths[language].read_bytes()
        rendered_spec = json.loads(spec_bytes)
        if rendered_spec != specs[language]:
            raise AssertionError(f"{language} input spec changed while planning")
        if rendered_spec.get("info", {}).get("version") != expected_info_version:
            raise AssertionError(f"{language} rendered spec has the wrong info.version")
        planned_writes[
            root / "api-reference" / stable_spec_names[language]
        ] = spec_bytes
        suffix = "" if language == "en" else f".{language}"
        planned_writes[
            root / "api-reference" / new_version / f"openapi-{new_version}{suffix}.json"
        ] = spec_bytes

    for language in LANGUAGES:
        suffix = "" if language == "en" else f".{language}"
        spec_url = f"/api-reference/{new_version}/openapi-{new_version}{suffix}.json"
        target_base = api_base(root, language) / new_version
        for slug, source in stable[language].items():
            rendered_stub = snapshot_stub_text(source.read_text(), spec_url)
            if language != "en" and f"openapi-{new_version}.{language}.json" not in rendered_stub:
                raise AssertionError(
                    f"{language} rendered stub does not point at its localized spec: {slug}"
                )
            planned_writes[target_base / f"{slug}.mdx"] = rendered_stub.encode()

    for path, text in changelog_changes.items():
        planned_writes[path] = text.encode()
    planned_writes[root / "docs.json"] = dump_json(planned_docs).encode()
    planned_writes[history / "state.json"] = dump_json(planned_state).encode()
    planned_writes[history / "urls.json"] = dump_json(planned_inventory).encode()

    deletion_paths = [root / path for path in sorted(retired_paths)]
    overlap = set(planned_writes) & set(deletion_paths)
    if overlap:
        raise AssertionError(
            "release plan writes and deletes the same paths: "
            + ", ".join(path.relative_to(root).as_posix() for path in sorted(overlap))
        )

    tracked_result = run(["git", "ls-files", "-z"], root)
    if tracked_result.returncode != 0:
        raise RuntimeError(tracked_result.stderr.strip() or "git ls-files failed")
    tracked = set(tracked_result.stdout.rstrip("\0").split("\0"))
    planned_created_paths = sorted(
        (
            path for path in planned_writes
            if path.relative_to(root).as_posix() not in tracked
        ),
        key=lambda path: path.as_posix(),
    )
    unexpected_untracked = [
        path for path in deletion_paths
        if path.relative_to(root).as_posix() not in tracked
    ] + [path for path in planned_created_paths if path.exists() or path.is_symlink()]
    if unexpected_untracked:
        raise AssertionError(
            "release plan would overwrite or delete untracked files: "
            + ", ".join(
                path.relative_to(root).as_posix() for path in unexpected_untracked
            )
        )

    print("Release plan")
    print(f"- version: {current_version} -> {new_version}")
    for language in LANGUAGES:
        print(f"- {language} spec: {spec_paths[language]}")
    print(f"- create snapshot: {new_version} ({len(stable['en'])} stubs per language)")
    print(f"- retire snapshot: {retired_version} ({len(retired_paths)} files)")
    for language in LANGUAGES:
        print(
            f"  - {language}: create "
            f"{(api_base(root, language) / new_version).relative_to(root)}; remove "
            f"{(api_base(root, language) / retired_version).relative_to(root)}"
        )
    print(f"- dropdown labels: {', '.join(planned_labels)}")
    print(f"- redirect rules added: {len(old_only_rules) + len(wildcard_rules)}")
    for rule in sorted(old_only_rules + wildcard_rules, key=lambda item: item["source"]):
        print(f"  - {rule['source']} -> {rule['destination']}")
    print(f"- inventory URLs refreshed at {head_sha}: {len(retired_paths)}")
    print(f"- OpenAPI specs after release: {len(planned_specs)}")
    print("- changelogs rewritten: " + ", ".join(
        path.relative_to(root).as_posix() for path in sorted(changelog_changes)
    ))
    if args.dry_run:
        print("DRY RUN: no files changed")
        return 0

    tracked_mutations: list[str] = []
    created_mutations: list[Path] = []
    try:
        for path in deletion_paths:
            relative = path.relative_to(root).as_posix()
            tracked_mutations.append(relative)
            path.unlink()
        retired_directories = sorted(
            {
                parent
                for path in deletion_paths
                for parent in path.parents
                if parent != root and root in parent.parents
            },
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in retired_directories:
            try:
                directory.rmdir()
            except OSError:
                pass
        for path, content in planned_writes.items():
            relative = path.relative_to(root).as_posix()
            if relative not in tracked and (path.exists() or path.is_symlink()):
                raise RuntimeError(
                    f"planned created path appeared during apply: {relative}"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in tracked:
                tracked_mutations.append(relative)
            try:
                path.write_bytes(content)
            except Exception:
                if relative not in tracked and (path.exists() or path.is_symlink()):
                    created_mutations.append(path)
                raise
            if relative not in tracked:
                created_mutations.append(path)

        post_checker = run(
            [sys.executable, str(history / "check_redirects.py"), "--root", str(root)],
            root,
        )
        i18n = run([sys.executable, str(root / ".github/check-i18n-pages.py")], root)
        if post_checker.stdout:
            print(post_checker.stdout.rstrip())
        if i18n.stdout:
            print(i18n.stdout.rstrip())
        if post_checker.returncode != 0 or i18n.returncode != 0:
            if post_checker.stderr:
                print(post_checker.stderr.rstrip(), file=sys.stderr)
            if i18n.stderr:
                print(i18n.stderr.rstrip(), file=sys.stderr)
            raise RuntimeError("post-write release checks failed")
    except Exception as exc:
        rollback_errors = restore_tree(
            root,
            sorted(set(tracked_mutations)),
            created_mutations,
        )
        print(f"Release failed after writing; restored the tree: {exc}", file=sys.stderr)
        for rollback_error in rollback_errors:
            print(f"Rollback error: {rollback_error}", file=sys.stderr)
        return 2

    changed = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], root)
    added = removed = modified = 0
    for line in changed.stdout.splitlines():
        code = line[:2]
        if "D" in code:
            removed += 1
        elif code == "??" or "A" in code:
            added += 1
        else:
            modified += 1
    print("Release summary")
    print(f"- files: {added} added, {removed} removed, {modified} modified")
    print(f"- redirect rules added: {len(old_only_rules) + len(wildcard_rules)}")
    print(f"- labels: {', '.join(planned_labels)}")
    print("Remaining manual steps")
    print(f"- Add the changelog entry for {new_version} linking /api-reference/{new_version}/openapi-{new_version}.json.")
    print(f"- Update the main app repository public/openapi.json info.version to {new_version[1:]}.")
    print("- Before merging, run sweep.py against the PR preview and inspect the reference pages.")
    return 0


def main() -> int:
    try:
        return release_main()
    except Exception as exc:
        print(f"PRECONDITION FAILED (planning exception)\n- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
