"""Build and validate version-specific API navigation."""

from __future__ import annotations

import re


VERSION = re.compile(r"v\d{2}\.\d{2}\.\d{2}$")


def locale_prefix(language: str) -> str:
    return "" if language == "en" else f"{language}/"


def page_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from page_values(item)
    elif isinstance(value, dict) and "pages" in value:
        yield from page_values(value["pages"])


def api_page_slug(page: str, language: str) -> str | None:
    prefix = f"{locale_prefix(language)}api-reference/"
    normalized = page.lstrip("/")
    if not normalized.startswith(prefix):
        return None
    remainder = normalized[len(prefix):]
    first, separator, rest = remainder.partition("/")
    if VERSION.fullmatch(first):
        remainder = rest if separator else ""
    return remainder or None


def api_tab_index(tabs: list[dict], language: str) -> int:
    candidates = [
        index
        for index, tab in enumerate(tabs)
        if any(
            api_page_slug(page, language) is not None
            for page in page_values(tab.get("groups", []))
        )
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one API tab for {language}, found {len(candidates)}"
        )
    return candidates[0]


def navigation_api_pages(version_entry: dict, language: str) -> list[str]:
    tabs = version_entry.get("tabs", [])
    index = api_tab_index(tabs, language)
    return [
        page
        for page in page_values(tabs[index].get("groups", []))
        if api_page_slug(page, language) is not None
    ]


def expected_navigation_pages(slugs: set[str], language: str) -> list[str]:
    prefix = f"{locale_prefix(language)}api-reference/"
    return [prefix + slug for slug in sorted(slugs)]


def merge_order(base: list[str], incoming: list[str]) -> None:
    """Merge unseen values beside the neighbours from their first navigation."""
    for incoming_index, item in enumerate(incoming):
        positions = {existing: index for index, existing in enumerate(base)}
        if item in positions:
            continue

        insert_at = len(base)
        later_keys = incoming[incoming_index + 1:]
        later_position = next(
            (positions[candidate] for candidate in later_keys if candidate in positions),
            None,
        )
        if later_position is not None:
            insert_at = later_position
        else:
            earlier_keys = incoming[:incoming_index]
            earlier_position = next(
                (
                    positions[candidate]
                    for candidate in reversed(earlier_keys)
                    if candidate in positions
                ),
                None,
            )
            if earlier_position is not None:
                insert_at = earlier_position + 1
        base.insert(insert_at, item)


def tab_order(tab: dict, language: str) -> tuple[list[str], dict[str, list[str]]]:
    groups: list[str] = []
    pages: dict[str, list[str]] = {}
    for page in page_values(tab.get("groups", [])):
        slug = api_page_slug(page, language)
        if slug is None:
            continue
        group, separator, _ = slug.partition("/")
        if not separator:
            raise ValueError(f"API page has no group folder: {page}")
        if group not in pages:
            groups.append(group)
            pages[group] = []
        if slug not in pages[group]:
            pages[group].append(slug)
    return groups, pages


def group_templates(tab: dict, language: str) -> dict[str, dict]:
    """Return the innermost navigation group metadata for each folder."""
    templates: dict[str, dict] = {}

    def visit(value) -> set[str]:
        if isinstance(value, str):
            slug = api_page_slug(value, language)
            return {slug.split("/", 1)[0]} if slug and "/" in slug else set()
        if isinstance(value, list):
            folders: set[str] = set()
            for item in value:
                folders.update(visit(item))
            return folders
        if isinstance(value, dict) and isinstance(value.get("pages"), list):
            folders = visit(value["pages"])
            if len(folders) == 1:
                folder = next(iter(folders))
                templates.setdefault(
                    folder,
                    {key: item for key, item in value.items() if key != "pages"},
                )
            return folders
        return set()

    visit(tab.get("groups", []))
    return templates


def endpoint_wrapper(tab: dict, language: str) -> dict:
    """Preserve the outer API group metadata without retaining any page source."""
    candidates: list[tuple[int, dict]] = []

    def visit(value) -> set[str]:
        if isinstance(value, str):
            slug = api_page_slug(value, language)
            return {slug.split("/", 1)[0]} if slug and "/" in slug else set()
        if isinstance(value, list):
            folders: set[str] = set()
            for item in value:
                folders.update(visit(item))
            return folders
        if isinstance(value, dict) and isinstance(value.get("pages"), list):
            folders = visit(value["pages"])
            if folders:
                candidates.append(
                    (
                        len(folders),
                        {key: item for key, item in value.items() if key != "pages"},
                    )
                )
            return folders
        return set()

    visit(tab.get("groups", []))
    if not candidates:
        raise ValueError(f"API tab for {language} has no group wrapper")
    return max(reversed(candidates), key=lambda candidate: candidate[0])[1]


def snapshot_api_tab(
    versions: list[dict],
    language: str,
    version: str,
    desired_slugs: set[str],
    pre_release_first: dict | None = None,
) -> dict:
    first_tabs = versions[0]["tabs"]
    first_index = api_tab_index(first_tabs, language)
    first_tab = first_tabs[first_index]
    sources = [first_tab]
    for historical in versions[1:]:
        tabs = historical.get("tabs", [])
        sources.append(tabs[api_tab_index(tabs, language)])
    if pre_release_first is not None:
        tabs = pre_release_first.get("tabs", [])
        sources.append(tabs[api_tab_index(tabs, language)])

    desired_groups = {slug.split("/", 1)[0] for slug in desired_slugs if "/" in slug}
    if not desired_slugs or len(desired_groups) == 0:
        raise ValueError(f"cannot build API navigation for {language} {version}")

    ordered_groups: list[str] = []
    ordered_pages: dict[str, list[str]] = {}
    templates: dict[str, dict] = {}
    for source in sources:
        source_groups, source_pages = tab_order(source, language)
        merge_order(ordered_groups, source_groups)
        for group, pages in source_pages.items():
            merge_order(ordered_pages.setdefault(group, []), pages)
        for group, template in group_templates(source, language).items():
            templates.setdefault(group, template)

    ordered_groups = [group for group in ordered_groups if group in desired_groups]
    ordered_groups.extend(sorted(desired_groups - set(ordered_groups)))
    prefix = f"{locale_prefix(language)}api-reference/{version}/"
    planned_folder_groups = []
    for group in ordered_groups:
        desired_pages = {slug for slug in desired_slugs if slug.startswith(group + "/")}
        pages = [slug for slug in ordered_pages.get(group, []) if slug in desired_pages]
        pages.extend(sorted(desired_pages - set(pages)))
        template = dict(templates.get(group, {"group": group.replace("-", " ").title()}))
        template["pages"] = [prefix + slug for slug in pages]
        planned_folder_groups.append(template)

    planned = {key: item for key, item in first_tab.items() if key != "groups"}
    wrapper = endpoint_wrapper(first_tab, language)
    wrapper["pages"] = planned_folder_groups
    planned["groups"] = [wrapper]
    actual_slugs = {api_page_slug(page, language) for page in page_values(planned["groups"])}
    if actual_slugs != desired_slugs:
        missing = sorted(desired_slugs - actual_slugs)
        extra = sorted(actual_slugs - desired_slugs)
        raise ValueError(
            f"cannot place every {language} {version} snapshot page; "
            f"missing={missing}, extra={extra}"
        )
    return planned
