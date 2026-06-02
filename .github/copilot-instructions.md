# Firma.dev API Documentation — Copilot Instructions

Official documentation for the **Firma.dev API** (a document e-signing platform), built with Mintlify. Always call the product "Firma.dev API" or "Firma API" — never "partner api".

This file is intentionally thin: it points to the authoritative, always-current sources rather than copying them. Duplicated version tables and endpoint lists drift out of date (they have before), so they live in one place only.

## Where the details live

| You need… | Source of truth |
|---|---|
| Writing standards, frontmatter rules, the no-`#`-H1 rule, code-example rules, the "Do not" list, git workflow, product naming | `CLAUDE.md` (repo root) |
| Navigation — which guides exist, the API version list, and the endpoint groups in each version | `docs.json` |
| API version history, per-version changes, migration notes, OpenAPI download links | `guides/api-changelog.mdx` |
| Per-version OpenAPI specs (reference pages generate from these) | `api-reference/vXX.YY.ZZ/openapi-vXX.YY.ZZ.json` — current version is the highest-numbered folder |

## Project structure (brief)

- MDX files with YAML frontmatter; `docs.json` drives navigation, theme, and settings; pages use Mintlify components.
- Each API version is a snapshot folder under `api-reference/`. When the spec changes, a new version folder is added; never hand-maintain the version list here.

## The rules that bite most often

- The frontmatter `title` renders as H1 — never use `#` in body content; start at `##`.
- Never write "partner api" — it's "Firma.dev API" or "Firma API".
- Internal links are relative; code blocks always have language tags; test examples before publishing.

For anything beyond these, defer to `CLAUDE.md` and the guides above.
