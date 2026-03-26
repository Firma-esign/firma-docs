# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working relationship

- Push back on ideas when warranted — cite sources and explain reasoning
- ALWAYS ask for clarification rather than making assumptions
- NEVER lie, guess, or make up information

## Naming

Always refer to this product as "Firma.dev API" or "Firma API". Never use "partner api".

## Content strategy

- Document just enough for user success — not too much, not too little
- Make content evergreen when possible
- Search for existing information before adding new content; avoid duplication unless strategic
- Check existing patterns for consistency
- Start by making the smallest reasonable changes

## Frontmatter requirements

All MDX pages must include:

```yaml
---
title: "Clear, descriptive page title"
description: "Concise summary for SEO/navigation"
---
```

Optional: `icon` (FontAwesome icon name, e.g., `"clock-rotate-left"`)

## Header rules for guides

The frontmatter `title` renders as H1 automatically. Therefore:

- **Never use `#` (H1)** inside guide body content
- **Start with `##` (H2)** as the first header
- Use `###`, `####`, etc. for nested sections

## Writing standards

- Second-person voice ("you")
- Prerequisites at start of procedural content
- Test all code examples before publishing
- Match style and formatting of existing pages
- Include both basic and advanced use cases
- Language tags on all code blocks
- Code examples in multiple languages when possible (Node.js and Python preferred)
- Alt text on all images
- Relative paths for internal links

## Git workflow

- NEVER use `--no-verify` when committing
- Ask how to handle uncommitted changes before starting
- Create a new branch when no clear branch exists for changes
- Commit frequently throughout development
- NEVER skip or disable pre-commit hooks

## Do not

- Skip frontmatter on any MDX file
- Use `#` (H1) headers in guide content
- Use absolute URLs for internal links
- Include untested code examples
- Reference endpoints or guides not included in `docs.json`
- Make assumptions — always ask for clarification
