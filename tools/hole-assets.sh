#!/usr/bin/env sh
# Laedt die lokal ausgelieferten Fremd-Assets. Bewusst kein CDN zur Laufzeit.
set -eu

VERSION="5.3.3"
ZIEL="$(dirname "$0")/../app/static/vendor"
URL="https://cdn.jsdelivr.net/npm/bootstrap@${VERSION}/dist/css/bootstrap.min.css"
ERWARTET="3c8f27e6009ccfd710a905e6dcf12d0ee3c6f2ac7da05b0572d3e0d12e736fc8"

mkdir -p "$ZIEL"
curl -fsSL --retry 5 --retry-delay 3 -o "$ZIEL/bootstrap.min.css" "$URL"

IST="$(sha256sum "$ZIEL/bootstrap.min.css" | cut -d' ' -f1)"
if [ "$IST" != "$ERWARTET" ]; then
    echo "Pruefsumme weicht ab: $IST (erwartet $ERWARTET)" >&2
    exit 1
fi
printf '%s  bootstrap.min.css\n' "$ERWARTET" > "$ZIEL/SHA256SUMS"
echo "bootstrap ${VERSION} geprueft und abgelegt."
