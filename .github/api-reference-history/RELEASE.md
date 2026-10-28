# API reference release checklist

## Prepare

- Start from a clean branch at the commit that still contains the snapshot which will retire.
- Export the English, Spanish, and French OpenAPI specifications. Confirm that each `info.version` is the new zero-padded version without the leading `v`.
- Add or remove stable endpoint stubs and update each language's first API-reference navigation tab so they exactly match the new English operations and one another.
- Add any retiring-only slug and its destination to `state.json`.
- Review and commit these preparation edits locally. This preparation commit must still contain the snapshot that will retire, and the worktree must be clean before generation starts.

## Generate

Preview the complete plan first:

```bash
python3 .github/api-reference-history/release.py \
  --version vNN.NN.NN \
  --spec en=../release-input/openapi.json \
  --spec es=../release-input/openapi.es.json \
  --spec fr=../release-input/openapi.fr.json \
  --dry-run
```

Remove `--dry-run` to generate the release from the clean preparation commit. The command must finish with both repository checks passing. Review the generated changes, then commit them as the direct child of the preparation commit. Push both commits together; the preparation commit is the immutable target used by the generated raw GitHub changelog links.

## Finish and verify

- Add the new changelog entry, linking `/api-reference/vNN.NN.NN/openapi-vNN.NN.NN.json`.
- Update `public/openapi.json` `info.version` in the main application repository.
- Review the generated diff, counts, navigation labels, redirects, noindex frontmatter, and raw changelog links.
- Run `sweep.py <preview-base-url>` against the pull-request preview and manually inspect stable and snapshot pages in all three languages.
- Merge only after the preview sweep passes. Use a fast-forward merge or another history-preserving merge. Never squash or rebase the preparation and generated-release commits: the changelog's raw GitHub URLs name the preparation commit.
- After merging, open a few generated raw GitHub changelog links in different languages and confirm that the retired specifications are still available at the named preparation commit.
- Watch the Mintlify deployment, then run `sweep.py https://docs.firma.dev` against the live site.
