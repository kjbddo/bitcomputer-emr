#!/usr/bin/env bash
# 매니페스트 기준으로 모델 가중치를 내려받고 SHA256을 검증한다.
set -euo pipefail

MANIFEST="$(dirname "$0")/models.manifest.tsv"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail=0
while IFS=$'\t' read -r path sha url; do
  case "$path" in ''|\#*) continue ;; esac

  dest="$ROOT/$path"
  mkdir -p "$(dirname "$dest")"

  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$sha" ]; then
    echo "ok (cached)  $path"
    continue
  fi

  echo "downloading  $path"
  downloaded=0

  # GitHub Release asset URL(https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>)은
  # private 저장소일 경우 인증 없이 curl로 받을 수 없다. gh CLI가 있으면 그쪽 인증을 재사용한다.
  if [[ "$url" =~ ^https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/]+)$ ]] \
      && command -v gh >/dev/null 2>&1; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    tag="${BASH_REMATCH[3]}"
    asset="${BASH_REMATCH[4]}"
    if gh release download "$tag" -R "$owner/$repo" -p "$asset" -O "$dest" --clobber >/dev/null 2>&1; then
      downloaded=1
    fi
  fi

  if [ "$downloaded" -ne 1 ] && curl -fsSL --retry 3 -o "$dest" "$url"; then
    downloaded=1
  fi

  if [ "$downloaded" -ne 1 ]; then
    echo "FAILED download: $path" >&2
    fail=1
    continue
  fi

  actual="$(sha256sum "$dest" | cut -d' ' -f1)"
  if [ "$actual" != "$sha" ]; then
    echo "FAILED checksum: $path" >&2
    echo "  expected $sha" >&2
    echo "  actual   $actual" >&2
    rm -f "$dest"
    fail=1
    continue
  fi
  echo "ok           $path"
done < "$MANIFEST"

exit "$fail"
