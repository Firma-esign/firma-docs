# Firma.dev API Documentation

Official documentation for the [Firma.dev](https://firma.dev) API — a document e-signing platform. Built with [Mintlify](https://mintlify.com).

## Project Structure

```
docs.json            # Navigation, theme, and site configuration
guides/              # Integration and usage guides (MDX)
api-reference/       # Versioned API reference pages (MDX + OpenAPI specs)
  v01.06.00/         # v1.6.0 (latest)
  v01.05.00/         # v1.5.0
  v01.04.00/         # v1.4.0
  v01.03.00/         # v1.3.0
  v01.02.00/         # v1.2.0
  v01.01.00/         # v1.1.0
  v01.00.02/         # v1.0.2
  v01.00.01/         # v1.0.1
snippets/            # Reusable MDX snippets
images/              # Static images
logo/                # Brand logos (light/dark)
scripts/             # Utility scripts
```

## Content

### Guides

Guides live in `guides/` as MDX files. They cover setup, authentication, workspace management, embeddable components, webhooks, and more.

### API Reference

Each API version has its own folder under `api-reference/` containing an OpenAPI spec file and generated MDX pages for each endpoint. Endpoint groups include Workspaces, Templates, Signing Requests, Custom Fields, Email Domains, Webhooks, JWT Management, and more.

### API Versions

| Version | Folder | Highlights |
|---------|--------|------------|
| v1.6.0 (latest) | `v01.06.00/` | Current release |
| v1.5.0 | `v01.05.00/` | Email validation warnings |
| v1.4.0 | `v01.04.00/` | New field types, PATCH field operations |
| v1.3.0 | `v01.03.00/` | Email Domains API |
| v1.2.0 | `v01.02.00/` | Enhanced user fields |
| v1.1.0 | `v01.01.00/` | Template CRUD, API key management |
| v1.0.2 | `v01.00.02/` | Custom Fields API |
| v1.0.1 | `v01.00.01/` | Initial release |

## Configuration

Site-wide settings — navigation, theme colors, versioning, and navbar — are defined in `docs.json`. Changes pushed to the default branch are deployed automatically via the Mintlify GitHub integration.