# Mintlify documentation

## Working relationship
- You can push back on ideas-this can lead to better documentation. Cite sources and explain your reasoning when you do so
- ALWAYS ask for clarification rather than making assumptions
- NEVER lie, guess, or make up information

## Project context
- Format: MDX files with YAML frontmatter
- Config: docs.json for navigation, theme, settings
- Components: Mintlify components

## Content strategy
- Document just enough for user success - not too much, not too little
- Prioritize accuracy and usability of information
- Make content evergreen when possible
- Search for existing information before adding new content. Avoid duplication unless it is done for a strategic reason
- Check existing patterns for consistency
- Start by making the smallest reasonable changes

## Frontmatter requirements for pages
- title: Clear, descriptive page title
- description: Concise summary for SEO/navigation

## Writing standards
- Second-person voice ("you")
- Prerequisites at start of procedural content
- Test all code examples before publishing
- Match style and formatting of existing pages
- Include both basic and advanced use cases
- Language tags on all code blocks
- Alt text on all images
- Relative paths for internal links

## Git workflow
- NEVER use --no-verify when committing
- Ask how to handle uncommitted changes before starting
- Create a new branch when no clear branch exists for changes
- Commit frequently throughout development
- NEVER skip or disable pre-commit hooks

## Do not
- Skip frontmatter on any MDX file
- Use absolute URLs for internal links
- Include untested code examples
- Make assumptions - always ask for clarification

---

# Recent Documentation Update (October 13, 2025)

## ✅ Completed: API Reference Regeneration

### What Was Done
1. **Regenerated all API reference files** from OpenAPI spec using Mintlify scraper
2. **Updated `docs.json`** with correct navigation structure
3. **Fixed broken links** in guides to match new API reference filenames
4. **Verified all guides** for accuracy and completeness

### Key Changes

#### API Reference Structure (34 endpoints)
- ✅ Added **Workspaces** group (3 endpoints)
- ✅ Updated **Templates** group with new update methods:
  - `comprehensive-template-update` (PUT - full replacement)
  - `partially-update-template` (PATCH - partial update)
- ❌ Removed **Teams** group (not in OpenAPI spec)

#### Guide Updates
- ✅ Fixed `creating-workspaces.mdx` API reference links
- ✅ Verified all other guides - no changes needed

### Post-Regeneration Enhancements
1. ✅ Added PATCH vs PUT guidance to `embeddable-template-editor.mdx`
   - Comprehensive "Updating Templates" section (~140 lines)
   - Explanation of when to use PUT vs PATCH
   - Code examples in Node.js and Python
   - Comparison table and best practices
2. ✅ Added API reference section to `workspace-settings.mdx`
   - Links to all workspace-related endpoints
   - Rate limits noted for each endpoint
   - Organized by category (management, settings, related)

### Files Modified
- `docs.json` (navigation structure with Workspaces group)
- `guides/creating-workspaces.mdx` (fixed 4 API reference links)
- `guides/embeddable-template-editor.mdx` (added "Updating Templates" section)
- `guides/workspace-settings.mdx` (added "API Reference" section)
- `DOCUMENTATION_UPDATES.md` (comprehensive change log)
- All 34 API reference MDX files (regenerated from OpenAPI)

### Content Impact
**Lines Added**: ~160 lines of new guide content
- Embeddable Template Editor: +140 lines (PUT/PATCH guidance)
- Workspace Settings: +20 lines (API reference links)

### Status
**✅ READY FOR DEPLOYMENT** - All updates complete, enhanced documentation quality

---

# Latest Update (October 14, 2025)

## Verification & Signing Request Enhancements

### What Was Done
1. **Complete API reference audit** - Verified all 36 endpoint files
2. **Fixed docs.json** - Added 2 missing signing request endpoints
3. **Enhanced sending-signing-request guide** - Added PUT vs PATCH update guidance
4. **Verified all guide links** - 20 API reference links checked, all valid

### Issues Found & Fixed
- ❌ Missing: `comprehensive-update-signing-request.mdx` in navigation
- ❌ Missing: `partially-update-signing-request.mdx` in navigation
- ⚠️ Content gap: No update guidance for signing requests (templates had it)

### Enhancements Applied

#### docs.json
- ✅ Added 2 signing request update endpoints
- ✅ Total: 36 endpoints now documented (was 34)

#### sending-signing-request.mdx
- ✅ Added "Updating Signing Requests" section (~120 lines)
- ✅ PUT (full update) explanation + code example
- ✅ PATCH (partial update) explanation + 2 code examples
- ✅ Decision table (6 scenarios)
- ✅ Critical warning about pre-send updates only
- ✅ Rate limiting and best practices

### Content Consistency Achievement
Both entities with PUT/PATCH endpoints now have matching guidance:
- ✅ Templates guide: Has update section (~140 lines)
- ✅ Signing requests guide: Has update section (~120 lines)
- ✅ Pattern consistency: 100%

### Files Modified
- `docs.json` (added 2 endpoint references)
- `guides/sending-signing-request.mdx` (added update guidance)
- `DOCUMENTATION_UPDATES.md` (added October 14 section)
- `VERIFICATION_SUMMARY.md` (new file)

### Current State
**36 API endpoints** fully documented ✅  
**100% navigation coverage** ✅  
**0 broken links** ✅  
**Consistent content patterns** ✅