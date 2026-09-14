#!/usr/bin/env bash
# Organization-seal docs guard (owner decision K3, 2026-09-13; counsel step closed by owner 2026-09-14).
# Guards three things per locale on the legal-validity page: the positive advanced-seal claim is present, no
# over-claiming wording appears anywhere else on the page, and the existing "does not provide" boundary sentence
# (already live and reviewed) has not been deleted by a later edit. Also pins the published API version and the
# guide header rules. Run from anywhere: bash .github/check-seal-docs.sh
set -euo pipefail; cd "$(dirname "$0")/.."

for f in api-reference/v01.37.00/openapi-v01.37.00.json api-reference/v01.37.00/openapi-v01.37.00.es.json api-reference/v01.37.00/openapi-v01.37.00.fr.json; do
  [ "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['info']['version'])" "$f")" = "01.37.00" ] || { echo "version drift in $f"; exit 1; }
done
python3 - <<'PY' || { echo "docs.json: v1.37.0 is not the first version in every language"; exit 1; }
import json; d=json.load(open('docs.json'))
assert all(l['versions'][0]['version']=='v1.37.0' for l in d['navigation']['languages']), 'v1.37.0 not first'
PY
# Naming rule scoped to the seal pages; historical changelog entries predate the rule and are left as-is.
! grep -qi "partner api" guides/organization-seals.mdx es/guides/organization-seals.mdx fr/guides/organization-seals.mdx \
    guides/legal-validity.mdx es/guides/legal-validity.mdx fr/guides/legal-validity.mdx || { echo "forbidden phrase: partner api"; exit 1; }
for g in guides/organization-seals.mdx es/guides/organization-seals.mdx fr/guides/organization-seals.mdx; do
  ! grep -q '^# ' "$g" || { echo "H1 in $g"; exit 1; }
  grep -q '^title:' "$g" && grep -q '^description:' "$g" || { echo "frontmatter missing in $g"; exit 1; }
done

check_legal () {  # $1 = file, $2 = positive claim, $3 = boundary sentence that must survive, $4.. = forbidden claim regexes
  local file="$1" claim="$2" boundary="$3"; shift 3
  grep -qF "$claim" "$file"    || { echo "missing the advanced-seal claim in $file"; exit 1; }
  grep -qF "$boundary" "$file" || { echo "the existing 'does not provide' boundary sentence is gone from $file"; exit 1; }
  local stripped; stripped="$(grep -vF "$claim" "$file" | grep -vF "$boundary")"
  for phrase in "$@"; do
    if grep -qiE "$phrase" <<<"$stripped"; then echo "forbidden claim matching /$phrase/ in $file"; exit 1; fi
  done
}
check_legal guides/legal-validity.mdx \
  "Together, this gives you a seal that is uniquely linked to your company, backed by an attested authority chain, and provably unaltered since application - the criteria that define an advanced electronic seal under Article 36." \
  "Firma does not produce Qualified Electronic Signatures (QES) or Qualified Electronic Seals." \
  "(firma|our|the) [a-z ]*seal[a-z ]* is [a-z ]*qualified" "qualified electronic seal (is )?(provided|offered|issued) by"
check_legal es/guides/legal-validity.mdx \
  "En conjunto, esto te da un sello vinculado de forma única a tu empresa, respaldado por una cadena de autoridad atestiguada, y demostrablemente inalterado desde su aplicación - los criterios que definen un sello electrónico avanzado conforme al Artículo 36." \
  "Firma no genera Firmas Electrónicas Cualificadas (QES) ni Sellos Electrónicos Cualificados." \
  "sello[a-z ]* (de firma )?(es|son) [a-z ]*(cualificad|reconocid)" "sello electronico (cualificado|reconocido) (de|que ofrece) firma"
check_legal fr/guides/legal-validity.mdx \
  "Ensemble, cela vous donne un cachet lié de manière univoque à votre entreprise, adossé à une chaîne d'autorité attestée, et dont l'intégrité est vérifiable depuis son application - les critères qui définissent un cachet électronique avancé au titre de l'article 36." \
  "Firma ne produit pas de Signatures Électroniques Qualifiées (QES) ni de Cachets Électroniques Qualifiés." \
  "cachet[a-z ]* (est|sont) [a-z ]*qualifiee?s?" "cachet electronique qualifiee?s? (de|fourni par) firma"
# A seal is never described as signing (D4/D6):
for f in guides/legal-validity.mdx guides/organization-seals.mdx; do
  ! grep -qiE "\bseal (is )?signed\b" "$f" || { echo "a seal is never described as signing in $f"; exit 1; }
done
echo ok
