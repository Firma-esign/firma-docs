#!/usr/bin/env python3
"""End-to-end rehearsal tests for the API-reference release tool."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

from release_navigation import snapshot_api_tab


NEW_VERSION = "v01.40.05"
SECOND_NEW_VERSION = "v01.40.06"
RETIRED_VERSION = "v01.39.00"
LANGUAGES = ("en", "es", "fr")


def command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


class ReleaseRehearsalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = Path(__file__).resolve().parents[2]
        cls.temporary = tempfile.TemporaryDirectory()
        cls.suite_root = Path(cls.temporary.name)
        cls.baseline = cls.suite_root / "baseline"
        shutil.copytree(
            cls.source,
            cls.baseline,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        cls.git(cls.baseline, "init", "-q")
        cls.git(cls.baseline, "config", "user.name", "Release Test")
        cls.git(cls.baseline, "config", "user.email", "release-test@example.invalid")
        cls.git(cls.baseline, "add", ".")
        cls.git(cls.baseline, "commit", "-qm", "baseline")
        inventory = json.loads(
            (cls.baseline / ".github/api-reference-history/urls.json").read_text()
        )
        for index, sha in enumerate(inventory["generated_from"]):
            cls.git(
                cls.baseline,
                "fetch",
                "-q",
                str(cls.source),
                f"{sha}:refs/tags/history-origin-{index}",
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def git(cls, cwd: Path, *args: str) -> str:
        result = command(["git", *args], cwd)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        return result.stdout.strip()

    def clone_case(self, name: str) -> Path:
        target = self.suite_root / name
        result = command(
            ["git", "clone", "-q", "--no-local", str(self.baseline), str(target)],
            self.suite_root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git(target, "config", "user.name", "Release Test")
        self.git(target, "config", "user.email", "release-test@example.invalid")
        return target

    def make_specs(
        self,
        case: Path,
        name: str,
        version: str = NEW_VERSION,
    ) -> dict[str, Path]:
        destination = self.suite_root / f"{name}-specs"
        destination.mkdir()
        result: dict[str, Path] = {}
        names = {"en": "openapi.json", "es": "openapi.es.json", "fr": "openapi.fr.json"}
        for language in LANGUAGES:
            data = json.loads((case / "api-reference" / names[language]).read_text())
            data["info"]["version"] = version[1:]
            path = destination / f"{language}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            result[language] = path
        return result

    def run_release(
        self,
        case: Path,
        specs: dict[str, Path],
        *extra: str,
        version: str = NEW_VERSION,
    ) -> subprocess.CompletedProcess[str]:
        script = case / ".github/api-reference-history/release.py"
        args = [
            "python3",
            str(script),
            "--version",
            version,
        ]
        for language in LANGUAGES:
            args.extend(["--spec", f"{language}={specs[language]}"])
        args.extend(extra)
        return command(args, case)

    def tree_fingerprint(self, case: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(case.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            digest.update(path.relative_to(case).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def tracked_tree_fingerprint(self, case: Path) -> str:
        digest = hashlib.sha256()
        tracked = self.git(case, "ls-files", "-z").split("\0")
        for relative in sorted(path for path in tracked if path):
            digest.update(relative.encode())
            digest.update((case / relative).read_bytes())
        return digest.hexdigest()

    def page_values(self, value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from self.page_values(item)
        elif isinstance(value, dict) and "pages" in value:
            yield from self.page_values(value["pages"])

    def navigation_api_pages(self, case: Path, language: str, index: int) -> list[str]:
        docs = json.loads((case / "docs.json").read_text())
        block = next(
            item for item in docs["navigation"]["languages"]
            if item["language"] == language
        )
        prefix = f"{'' if language == 'en' else language + '/'}api-reference/"
        candidates = []
        for tab in block["versions"][index]["tabs"]:
            pages = [
                page for page in self.page_values(tab.get("groups", []))
                if page.startswith(prefix)
            ]
            if pages:
                candidates.append(pages)
        self.assertEqual(len(candidates), 1)
        return candidates[0]

    def snapshot_navigation_pages(
        self, case: Path, language: str, version: str
    ) -> list[str]:
        locale = Path() if language == "en" else Path(language)
        base = case / locale / "api-reference" / version
        prefix = f"{'' if language == 'en' else language + '/'}api-reference/{version}/"
        return sorted(
            prefix + path.relative_to(base).with_suffix("").as_posix()
            for path in base.rglob("*.mdx")
        )

    def update_first_navigation(
        self,
        case: Path,
        old_suffix: str,
        new_page: str | None,
    ) -> None:
        docs_path = case / "docs.json"
        docs = json.loads(docs_path.read_text())
        for block in docs["navigation"]["languages"]:
            language = block["language"]
            prefix = f"{'' if language == 'en' else language + '/'}api-reference/"
            replaced = False

            def visit(value) -> None:
                nonlocal replaced
                if not isinstance(value, list):
                    return
                for index, item in enumerate(list(value)):
                    if isinstance(item, str) and item.endswith(old_suffix):
                        replaced = True
                        if new_page is None:
                            value.pop(index)
                        else:
                            value.insert(index + 1, prefix + new_page)
                        return
                    if isinstance(item, dict):
                        visit(item.get("pages", []))
                        if replaced:
                            return

            for tab in block["versions"][0]["tabs"]:
                visit(tab.get("groups", []))
                if replaced:
                    break
            self.assertTrue(replaced, f"navigation page not found for {language}: {old_suffix}")
        docs_path.write_text(json.dumps(docs, ensure_ascii=False, indent=2) + "\n")

    def assert_fail_closed(
        self,
        case: Path,
        specs: dict[str, Path],
        expected_message: str,
    ) -> None:
        before = self.tree_fingerprint(case)
        result = self.run_release(case, specs)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(expected_message, result.stderr)
        self.assertEqual(self.tree_fingerprint(case), before)

    def test_end_to_end_release(self) -> None:
        case = self.clone_case("success")
        specs = self.make_specs(case, "success")
        head_sha = self.git(case, "rev-parse", "HEAD")

        result = self.run_release(case, specs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        docs = json.loads((case / "docs.json").read_text())
        labels = [
            "v1.40.5 (latest)",
            "v1.40.4",
            "v1.40.2",
            "v1.40.1",
            "v1.40.0",
            "v1.39.1",
        ]
        for language in docs["navigation"]["languages"]:
            self.assertEqual([item["version"] for item in language["versions"]], labels)

        for language in LANGUAGES:
            locale = Path() if language == "en" else Path(language)
            folder = case / locale / "api-reference" / NEW_VERSION
            stubs = sorted(folder.rglob("*.mdx"))
            self.assertEqual(len(stubs), 124)
            for stub in stubs:
                text = stub.read_text()
                self.assertEqual(text.count("noindex: true"), 1)
                self.assertTrue(text.endswith("---"))
                self.assertFalse(text.endswith("---\n"))
                suffix = "" if language == "en" else f".{language}"
                self.assertIn(
                    f"/api-reference/{NEW_VERSION}/openapi-{NEW_VERSION}{suffix}.json",
                    text,
                )
            self.assertFalse((case / locale / "api-reference" / RETIRED_VERSION).exists())

        stable_names = {"en": "openapi.json", "es": "openapi.es.json", "fr": "openapi.fr.json"}
        for language in LANGUAGES:
            expected_spec = json.loads(specs[language].read_text())
            suffix = "" if language == "en" else f".{language}"
            stable_spec = json.loads(
                (case / "api-reference" / stable_names[language]).read_text()
            )
            snapshot_spec = json.loads(
                (
                    case
                    / "api-reference"
                    / NEW_VERSION
                    / f"openapi-{NEW_VERSION}{suffix}.json"
                ).read_text()
            )
            self.assertEqual(stable_spec, expected_spec)
            self.assertEqual(snapshot_spec, expected_spec)
            self.assertEqual(stable_spec["info"]["version"], NEW_VERSION[1:])
            self.assertEqual(snapshot_spec["info"]["version"], NEW_VERSION[1:])

        specs_on_disk = [
            path for path in case.rglob("openapi*.json")
            if ".git" not in path.parts
        ]
        self.assertEqual(len(specs_on_disk), 21)

        rules = {rule["source"]: rule for rule in docs["redirects"]}
        inventory = json.loads(
            (case / ".github/api-reference-history/urls.json").read_text()
        )
        retired_entries = [
            entry for entry in inventory["entries"]
            if f"/{RETIRED_VERSION}/" in f"/{entry['path']}"
        ]
        self.assertEqual(len(retired_entries), 375)
        self.assertTrue(all(entry["origin_sha"] == head_sha for entry in retired_entries))
        for language in LANGUAGES:
            prefix = "" if language == "en" else f"{language}/"
            page_prefix = f"{prefix}api-reference/{RETIRED_VERSION}/"
            groups = {
                entry["path"].removeprefix(page_prefix).split("/", 1)[0]
                for entry in retired_entries
                if entry["kind"] == "page" and entry["path"].startswith(page_prefix)
            }
            self.assertTrue(groups)
            for group in groups:
                source = f"/{prefix}api-reference/{RETIRED_VERSION}/{group}/:slug*"
                destination = f"/{prefix}api-reference/{group}/:slug*"
                self.assertEqual(rules[source]["destination"], destination)

        suffixes = {"en": "", "es": ".es", "fr": ".fr"}
        for language in LANGUAGES:
            locale = Path() if language == "en" else Path(language)
            changelog = (case / locale / "guides/api-changelog.mdx").read_text()
            expected = (
                "https://raw.githubusercontent.com/Firma-esign/firma-docs/"
                f"{head_sha}/api-reference/{RETIRED_VERSION}/"
                f"openapi-{RETIRED_VERSION}{suffixes[language]}.json"
            )
            self.assertIn(expected, changelog)

        checker = command(
            ["python3", ".github/api-reference-history/check_redirects.py"], case
        )
        self.assertEqual(checker.returncode, 0, checker.stdout + checker.stderr)
        self.assertIn("PASS:", checker.stdout)

    def test_dry_run_changes_nothing(self) -> None:
        case = self.clone_case("dry-run")
        specs = self.make_specs(case, "dry-run")
        before = self.tree_fingerprint(case)
        result = self.run_release(case, specs, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY RUN: no files changed", result.stdout)
        self.assertEqual(self.tree_fingerprint(case), before)

    def test_new_operation_without_stub_is_fail_closed(self) -> None:
        case = self.clone_case("missing-stub")
        specs = self.make_specs(case, "missing-stub")
        data = json.loads(specs["en"].read_text())
        data["paths"]["/__release-test-missing"] = {
            "get": {"responses": {"200": {"description": "ok"}}}
        }
        specs["en"].write_text(json.dumps(data, indent=2) + "\n")
        self.assert_fail_closed(case, specs, "new English operation has no stable stub")

    def test_stub_whose_operation_is_gone_is_fail_closed(self) -> None:
        case = self.clone_case("missing-operation")
        specs = self.make_specs(case, "missing-operation")
        data = json.loads(specs["en"].read_text())
        del data["paths"]["/templates"]["get"]
        specs["en"].write_text(json.dumps(data, indent=2) + "\n")
        self.assert_fail_closed(
            case,
            specs,
            "stable English stub points at an operation absent from the new spec",
        )

    def test_wrong_info_version_is_fail_closed(self) -> None:
        case = self.clone_case("wrong-version")
        specs = self.make_specs(case, "wrong-version")
        data = json.loads(specs["fr"].read_text())
        data["info"]["version"] = "01.40.04"
        specs["fr"].write_text(json.dumps(data, indent=2) + "\n")
        self.assert_fail_closed(case, specs, "fr spec info.version")

    def test_dirty_worktree_is_fail_closed(self) -> None:
        case = self.clone_case("dirty")
        specs = self.make_specs(case, "dirty")
        (case / "dirty-marker.txt").write_text("dirty\n")
        self.assert_fail_closed(case, specs, "worktree is not clean")

    def test_missing_old_only_mapping_is_fail_closed(self) -> None:
        case = self.clone_case("missing-old-only")
        specs = self.make_specs(case, "missing-old-only")
        stub = case / "api-reference" / RETIRED_VERSION / "retired-only/missing-map.mdx"
        stub.parent.mkdir(parents=True)
        stub.write_text(
            "---\n"
            "noindex: true\n"
            f"openapi: /api-reference/{RETIRED_VERSION}/openapi-{RETIRED_VERSION}.json get /templates\n"
            "---"
        )
        self.git(case, "add", str(stub.relative_to(case)))
        self.git(case, "commit", "-qm", "add retired-only rehearsal stub")
        self.assert_fail_closed(
            case,
            specs,
            "retired en slug is missing from state old_only_slugs: retired-only/missing-map",
        )

    def test_stable_stub_body_is_fail_closed_and_tree_unchanged(self) -> None:
        case = self.clone_case("stub-body")
        stub = case / "api-reference/templates/list-templates.mdx"
        stub.write_text(stub.read_text() + "\nbody content after frontmatter\n")
        self.git(case, "add", str(stub.relative_to(case)))
        self.git(case, "commit", "-qm", "prepare malformed stable stub")
        specs = self.make_specs(case, "stub-body")
        self.assert_fail_closed(case, specs, "stub must contain one openapi line and end with ---")
        self.assertEqual(self.git(case, "status", "--porcelain"), "")

    def test_post_write_checker_failure_restores_exact_tree(self) -> None:
        case = self.clone_case("post-checker-rollback")
        checker = case / ".github/api-reference-history/check_redirects.py"
        text = checker.read_text()
        needle = "def main() -> int:\n"
        injected = (
            needle
            + "    release_root = Path(__file__).resolve().parents[2]\n"
            + f"    if (release_root / 'api-reference' / '{NEW_VERSION}').exists():\n"
            + "        print('FAIL (injected post-write checker failure)')\n"
            + "        return 1\n"
        )
        self.assertIn(needle, text)
        checker.write_text(text.replace(needle, injected, 1))
        self.git(case, "add", str(checker.relative_to(case)))
        self.git(case, "commit", "-qm", "inject post-write checker failure")
        specs = self.make_specs(case, "post-checker-rollback")
        before = self.tree_fingerprint(case)

        result = self.run_release(case, specs)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("restored the tree", result.stderr)
        self.assertEqual(self.git(case, "status", "--porcelain"), "")
        self.assertEqual(self.tree_fingerprint(case), before)

    def test_mid_apply_failure_restores_touched_paths_and_preserves_raced_file(self) -> None:
        case = self.clone_case("mid-apply-rollback")
        release = case / ".github/api-reference-history/release.py"
        text = release.read_text()
        needle = "        for path, content in planned_writes.items():\n"
        injected = (
            needle
            + "            injected = root / 'api-reference' / "
            + f"'{NEW_VERSION}' / 'openapi-{NEW_VERSION}.json'\n"
            + "            if path == injected:\n"
            + "                path.parent.mkdir(parents=True, exist_ok=True)\n"
            + "                path.write_bytes(b'unrelated raced file\\n')\n"
        )
        self.assertIn(needle, text)
        release.write_text(text.replace(needle, injected, 1))
        self.git(case, "add", str(release.relative_to(case)))
        self.git(case, "commit", "-qm", "inject mid-apply raced-file failure")

        raced_relative = f"api-reference/{NEW_VERSION}/openapi-{NEW_VERSION}.json"
        exclude = case / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + f"\n/{raced_relative}\n")
        specs = self.make_specs(case, "mid-apply-rollback")
        before = self.tracked_tree_fingerprint(case)

        result = self.run_release(case, specs)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("planned created path appeared during apply", result.stderr)
        self.assertIn("restored the tree", result.stderr)
        self.assertEqual((case / raced_relative).read_bytes(), b"unrelated raced file\n")
        self.assertEqual(self.git(case, "status", "--porcelain"), "")
        self.assertEqual(self.tracked_tree_fingerprint(case), before)

    def test_endpoint_addition_keeps_previous_snapshot_navigation(self) -> None:
        case = self.clone_case("endpoint-addition")
        specs = self.make_specs(case, "endpoint-addition")
        for language in LANGUAGES:
            data = json.loads(specs[language].read_text())
            data["paths"]["/__release-test-added"] = {
                "get": {"responses": {"200": {"description": "ok"}}}
            }
            specs[language].write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            locale = Path() if language == "en" else Path(language)
            suffix = "" if language == "en" else f".{language}"
            stub = case / locale / "api-reference/workspaces/release-test-added.mdx"
            stub.write_text(
                "---\n"
                "title: Release test added endpoint\n"
                f"openapi: /api-reference/openapi{suffix}.json get /__release-test-added\n"
                "---"
            )
        self.update_first_navigation(
            case,
            "workspaces/list-workspaces",
            "workspaces/release-test-added",
        )
        self.git(case, "add", "docs.json", "api-reference", "es/api-reference", "fr/api-reference")
        self.git(case, "commit", "-qm", "prepare endpoint addition")
        expected_previous = {
            language: self.snapshot_navigation_pages(case, language, "v01.40.04")
            for language in LANGUAGES
        }

        result = self.run_release(case, specs)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for language in LANGUAGES:
            self.assertEqual(
                sorted(self.navigation_api_pages(case, language, 1)),
                expected_previous[language],
            )

    def test_endpoint_removal_keeps_previous_snapshot_navigation(self) -> None:
        case = self.clone_case("endpoint-removal")
        specs = self.make_specs(case, "endpoint-removal")
        for language in LANGUAGES:
            data = json.loads(specs[language].read_text())
            del data["paths"]["/templates"]["get"]
            specs[language].write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            locale = Path() if language == "en" else Path(language)
            (case / locale / "api-reference/templates/list-templates.mdx").unlink()
        self.update_first_navigation(case, "templates/list-templates", None)
        state_path = case / ".github/api-reference-history/state.json"
        state = json.loads(state_path.read_text())
        state["old_only_slugs"]["templates/list-templates"] = {
            "en": "/api-reference/templates/create-template",
            "es": "/es/api-reference/templates/create-template",
            "fr": "/fr/api-reference/templates/create-template",
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        self.git(case, "add", "-A")
        self.git(case, "commit", "-qm", "prepare endpoint removal")
        expected_previous = {
            language: self.snapshot_navigation_pages(case, language, "v01.40.04")
            for language in LANGUAGES
        }

        result = self.run_release(case, specs)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for language in LANGUAGES:
            previous_pages = sorted(self.navigation_api_pages(case, language, 1))
            self.assertEqual(previous_pages, expected_previous[language])
            self.assertTrue(
                any(page.endswith("templates/list-templates") for page in previous_pages)
            )

    def test_added_then_removed_endpoint_survives_second_release_navigation(self) -> None:
        case = self.clone_case("two-release-endpoint-removal")
        slug = "workspaces/release-test-transient"
        operation = "/__release-test-transient"

        first_specs = self.make_specs(case, "two-release-first")
        for language in LANGUAGES:
            data = json.loads(first_specs[language].read_text())
            data["paths"][operation] = {
                "get": {"responses": {"200": {"description": "ok"}}}
            }
            first_specs[language].write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            locale = Path() if language == "en" else Path(language)
            suffix = "" if language == "en" else f".{language}"
            stub = case / locale / f"api-reference/{slug}.mdx"
            stub.write_text(
                "---\n"
                "title: Transient release test endpoint\n"
                f"openapi: /api-reference/openapi{suffix}.json get {operation}\n"
                "---"
            )
        self.update_first_navigation(
            case,
            "workspaces/list-workspaces",
            slug,
        )
        self.git(case, "add", "docs.json", "api-reference", "es/api-reference", "fr/api-reference")
        self.git(case, "commit", "-qm", "prepare transient endpoint addition")

        first_result = self.run_release(case, first_specs)
        self.assertEqual(first_result.returncode, 0, first_result.stdout + first_result.stderr)
        expected_order: dict[str, list[str]] = {}
        for language in LANGUAGES:
            locale_prefix = "" if language == "en" else f"{language}/"
            stable_prefix = f"{locale_prefix}api-reference/"
            versioned_prefix = f"{stable_prefix}{NEW_VERSION}/"
            expected_order[language] = [
                versioned_prefix + page.removeprefix(stable_prefix)
                for page in self.navigation_api_pages(case, language, 0)
            ]
        self.git(case, "add", "-A")
        self.git(case, "commit", "-qm", "generate first transient endpoint release")

        second_specs = self.make_specs(
            case,
            "two-release-second",
            SECOND_NEW_VERSION,
        )
        for language in LANGUAGES:
            data = json.loads(second_specs[language].read_text())
            del data["paths"][operation]
            second_specs[language].write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            locale = Path() if language == "en" else Path(language)
            (case / locale / f"api-reference/{slug}.mdx").unlink()
        self.update_first_navigation(case, slug, None)
        self.git(case, "add", "-A")
        self.git(case, "commit", "-qm", "prepare transient endpoint removal")

        expected_snapshot = {
            language: self.snapshot_navigation_pages(case, language, NEW_VERSION)
            for language in LANGUAGES
        }
        second_result = self.run_release(
            case,
            second_specs,
            version=SECOND_NEW_VERSION,
        )

        self.assertEqual(
            second_result.returncode,
            0,
            second_result.stdout + second_result.stderr,
        )
        for language in LANGUAGES:
            previous_pages = self.navigation_api_pages(case, language, 1)
            self.assertEqual(previous_pages, expected_order[language])
            self.assertEqual(sorted(previous_pages), expected_snapshot[language])
            self.assertTrue(any(page.endswith(slug) for page in previous_pages))

        checker = command(
            ["python3", ".github/api-reference-history/check_redirects.py"], case
        )
        self.assertEqual(checker.returncode, 0, checker.stdout + checker.stderr)
        self.assertIn("PASS:", checker.stdout)


class SweepUrlComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "sweep.py"
        spec = importlib.util.spec_from_file_location("api_reference_history_sweep", path)
        if spec is None or spec.loader is None:
            raise AssertionError("cannot load sweep.py")
        cls.sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.sweep)

    def test_redirect_to_another_host_fails_absolute_url_comparison(self) -> None:
        responses = [
            (302, "https://wrong.example/api-reference/templates/list-templates"),
            (200, None),
        ]
        with mock.patch.object(self.sweep, "request_status", side_effect=responses):
            _, error = self.sweep.sweep_one(
                "https://preview.example:443",
                "/api-reference/v01.38.00/templates/list-templates",
                "/api-reference/templates/list-templates",
                False,
            )
        self.assertIsNotNone(error)
        self.assertIn("wrong final page", error)
        self.assertIn("wrong.example", error)
        self.assertIn("preview.example", error)


class SnapshotNavigationTest(unittest.TestCase):
    def test_snapshot_only_groups_and_pages_append_alphabetically(self) -> None:
        versions = [
            {
                "tabs": [
                    {
                        "tab": "API reference",
                        "groups": [
                            {
                                "group": "Endpoints",
                                "pages": [
                                    {
                                        "group": "Known",
                                        "pages": [
                                            "api-reference/known/second",
                                            "api-reference/known/first",
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
        desired = {
            "known/second",
            "known/first",
            "known/snapshot-only-z",
            "known/snapshot-only-a",
            "unseen-z/page-z",
            "unseen-a/page-z",
            "unseen-a/page-a",
        }

        tab = snapshot_api_tab(versions, "en", NEW_VERSION, desired)

        folders = tab["groups"][0]["pages"]
        self.assertEqual(
            [folder["group"] for folder in folders],
            ["Known", "Unseen A", "Unseen Z"],
        )
        self.assertEqual(
            folders[0]["pages"],
            [
                f"api-reference/{NEW_VERSION}/known/second",
                f"api-reference/{NEW_VERSION}/known/first",
                f"api-reference/{NEW_VERSION}/known/snapshot-only-a",
                f"api-reference/{NEW_VERSION}/known/snapshot-only-z",
            ],
        )
        self.assertEqual(
            folders[1]["pages"],
            [
                f"api-reference/{NEW_VERSION}/unseen-a/page-a",
                f"api-reference/{NEW_VERSION}/unseen-a/page-z",
            ],
        )


if __name__ == "__main__":
    unittest.main()
