# Firma.dev API Documentation

This repository contains the official documentation for the Firma.dev API, a document e-signing platform. The documentation is built with Mintlify.

> **Important:** Always refer to this product as "Firma.dev API" or simply "Firma API". Never use the term "partner api".

## Project Structure

- **Format:** MDX files with YAML frontmatter
- **Config:** `docs.json` for navigation, theme, and settings
- **Components:** Mintlify components

## Header Rules for Guides

The page title in the frontmatter is automatically rendered as an H1 (`#`) header. Therefore:

- **Never use `#` (H1) headers** inside guide content
- **Always start with `##` (H2)** as the first header in the body
- Use `###`, `####`, etc. for nested sections

Example:
```mdx
---
title: "My Guide Title"
description: "Description here"
---

## First Section  <!-- Correct: starts with H2 -->

Content here...

### Subsection  <!-- H3 for nesting -->
```

## Included Guides

The following guides are included in the documentation (from `docs.json`):

| Guide | File |
|-------|------|
| Complete Setup Guide | `guides/complete-setup-guide.mdx` |
| Authentication | `guides/authentication.mdx` |
| API Versioning | `guides/api-versioning.mdx` |
| Creating Workspaces | `guides/creating-workspaces.mdx` |
| White Labeling | `guides/white-labeling.mdx` |
| Sending Signing Request | `guides/sending-signing-request.mdx` |
| Embeddable Template Editor | `guides/embeddable-template-editor.mdx` |
| Embeddable Signing Request Editor | `guides/embeddable-signing-request-editor.mdx` |
| Embeddable Signing | `guides/embeddable-signing.mdx` |
| Rate Limits | `guides/rate-limits.mdx` |
| Webhooks | `guides/webhooks.mdx` |
| API Changelog | `guides/api-changelog.mdx` |

**Note:** The `api-versioning.mdx` guide is only available in v1.0.2 and later.

## API Versions

The documentation supports multiple API versions:

| Version | Folder | Notes |
|---------|--------|-------|
| v1.11.0 (latest) | `api-reference/v01.11.00/` | File upload fields, anchor tags, field background colors, signing order default change |
| v1.10.0 | `api-reference/v01.10.00/` | Conditional fields, DOCX support, audit trail, signature frame control |
| v1.9.0 | `api-reference/v01.09.00/` | OTP verification, replace template document |
| v1.8.0 | `api-reference/v01.08.00/` | Email Templates API, language support, spec corrections |
| v1.7.0 | `api-reference/v01.07.00/` | Hand-drawn signatures, legacy settings fields |
| v1.6.0 | `api-reference/v01.06.00/` | Split PDF downloads, field type normalization |
| v1.5.0 | `api-reference/v01.05.00/` | Email validation warnings |
| v1.4.0 | `api-reference/v01.04.00/` | New field types, PATCH field operations |
| v1.3.0 | `api-reference/v01.03.00/` | Email Domains API added |
| v1.2.0 | `api-reference/v01.02.00/` | Enhanced user fields |
| v1.1.0 | `api-reference/v01.01.00/` | Template CRUD, API key management |
| v1.0.2 | `api-reference/v01.00.02/` | Custom Fields API added |
| v1.0.1 | `api-reference/v01.00.01/` | Initial release |

## API Endpoint Groups

### All Versions (v1.0.1+)

| Group | Endpoints |
|-------|-----------|
| **Workspaces** | list-workspaces, create-a-new-workspace, get-a-workspace, update-a-workspace, partially-update-a-workspace, regenerate-workspace-api-key, expire-pending-api-keys |
| **Templates** | list-templates, create-template, get-template, comprehensive-template-update, partially-update-template, delete-a-template, duplicate-template-into-signing-request, get-template-fields, get-template-users, get-template-reminders |
| **Signing Requests** | list-signing-requests, create-signing-request, get-signing-request, comprehensive-update-signing-request, partially-update-signing-request, cancel-a-signing-request, send-signing-request, resend-signing-request-to-specific-recipients, get-signing-request-fields, get-signing-request-users, get-signing-request-reminders, get-embedded-signing-request-data-jwt-authenticated, save-embedded-signing-request-jwt-authenticated, send-embedded-signing-request-jwt-authenticated |
| **Account/Company** | get-company-information, update-company-information, partially-update-company-information |
| **Webhooks** | list-webhooks, create-webhook, get-webhook, update-webhook, delete-a-webhook, test-a-webhook, get-webhook-secret-rotation-status, rotate-webhook-signing-secret |
| **JWT Management** | generate-jwt-token-for-embedding-templates, revoke-template-jwt-token, generate-jwt-token-for-signing-request, revoke-a-signing-request-jwt-token |
| **Legacy** | list-documents-legacy, create-document-legacy |

### v1.0.2+ Only

| Group | Endpoints |
|-------|-----------|
| **Custom Fields** | list-workspace-custom-fields, create-workspace-custom-field, update-workspace-custom-field, delete-workspace-custom-field, list-template-custom-fields, create-template-custom-field, delete-template-custom-field, list-signing-request-custom-fields, create-signing-request-custom-field, delete-signing-request-custom-field |

### v1.1.0+ Only

Additional signing request endpoints:
- create-and-send-signing-request-atomic

### v1.3.0+

| Group | Endpoints |
|-------|-----------|
| **Email Domains** | list-company-domains, add-company-domain, get-company-domain, delete-company-domain, verify-domain-ownership, finalize-domain-setup, verify-dns-records, set-primary-domain, list-workspace-domains, add-workspace-domain, get-workspace-domain, delete-workspace-domain, verify-workspace-domain-ownership, finalize-workspace-domain-setup, verify-workspace-domain-dns-records, set-primary-workspace-domain |

### v1.4.0+

New field types added:
- `textarea` - Multi-line text input
- `url` - Clickable URL fields (auto read-only)
- `radio_buttons` - Radio button selection (renamed from `radio`)

PATCH endpoints now support creating/updating individual fields.

### v1.5.0+

Signing request responses may include `warnings` or `warning` fields for email format validation (non-blocking).

### v1.6.0+

Split PDF downloads: `document_only_download_url`, `certificate_only_download_url` and corresponding error fields on `SigningRequest`. Field type normalization: `initial`/`initials` and `textarea`/`text_area` both accepted.

### v1.7.0+

New `hand_drawn_only` boolean in `SigningRequestSettings` to require hand-drawn signatures. Deprecated top-level integer settings fields (`use_signing_order`, `allow_download`, `allow_editing_before_sending`, `hand_drawn_only`, `attach_pdf_on_finish`) added to `SigningRequest` schema for backward compatibility.

### v1.8.0+

New **Email Templates** API group for customizing signing notification emails at workspace and company levels. Endpoints: list-workspace-email-templates, get-workspace-email-template, create-or-update-workspace-email-template, delete-workspace-email-template, list-company-email-templates, create-or-update-company-email-template, delete-company-email-template, get-default-email-templates, get-email-template-placeholders. New `language` field on `Company` and `WorkspaceSettings`. Template schema expanded with inline recipients/fields. Webhook schema includes failure tracking. Spec corrections for field names across multiple schemas.

### v1.9.0+

New `require_otp_verification` boolean (nullable) in `SigningRequestSettings`, `WorkspaceSettings`, and `Company` schemas. When `true`, signers must verify their email with a one-time code before accessing documents. `null` inherits from parent level. New `POST /templates/{id}/replace-document` endpoint for replacing a template's PDF while preserving field placements (requires matching page count and dimensions).

### v1.10.0+

Conditional field logic: new `required_conditions` and `visibility_conditions` properties on fields with `ConditionSet`, `ConditionGroup`, and `Condition` schemas. DOCX document support across all upload endpoints (auto-converted to PDF). New `GET /signing-requests/{id}/audit` endpoint for retrieving audit trails. New `show_signature_frame` boolean (nullable) in `SigningRequestSettings`, `WorkspaceSettings`, and `Company`. New `force_remove_conditions` parameter on user deletion for handling condition dependencies.

### v1.11.0+

New `file` field type for signer file uploads (images/PDF, validated by magic bytes, 10MB max). New `FileFormatRules` schema with `acceptedFileTypes` enum (`image_and_pdf`, `image`, `pdf`). New `AnchorTag` schema and `anchor_tags` array on signing request creation for automatic field placement via text markers in PDFs (document-based creation only, up to 100 tags). New `background_color` hex string property on all field types. **Breaking:** `use_signing_order` default changed from `false` to `true`.

## Frontmatter Requirements

All MDX pages must include:

```yaml
---
title: "Clear, descriptive page title"
description: "Concise summary for SEO/navigation"
---
```

Optional frontmatter:
- `icon`: FontAwesome icon name (e.g., `"clock-rotate-left"`)

## Writing Standards

- Use second-person voice ("you")
- Prerequisites at start of procedural content
- Test all code examples before publishing
- Match style and formatting of existing pages
- Include both basic and advanced use cases
- Language tags on all code blocks
- Alt text on all images
- Relative paths for internal links

## Code Examples

When providing code examples:
- Always include language tags (```javascript, ```python, etc.)
- Provide examples in multiple languages when possible (Node.js and Python preferred)
- Test all examples before including

## Do Not

- Use `#` (H1) headers in guide content (title is already H1)
- Use the term "partner api" - use "Firma.dev API" or "Firma API"
- Skip frontmatter on any MDX file
- Use absolute URLs for internal links
- Include untested code examples
- Reference endpoints or guides not included in `docs.json`

## OpenAPI Specs

Each API version has its OpenAPI specification file:
- `api-reference/v01.03.00/openapi-v01.03.00.json`
- `api-reference/v01.02.00/openapi-v01.02.00.json`
- `api-reference/v01.01.00/openapi-v01.01.00.json`
- `api-reference/v01.00.02/openapi-v01.00.02.json`
- `api-reference/v01.00.01/openapi-v01.00.01.json`

API reference pages are generated from these specs using the Mintlify scraper.

## Git Workflow

- Never use `--no-verify` when committing
- Create a new branch when no clear branch exists for changes
- Commit frequently throughout development
- Never skip or disable pre-commit hooks
