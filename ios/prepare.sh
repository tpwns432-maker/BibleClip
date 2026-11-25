#!/usr/bin/env bash
# 앱에 넣을 것을 ios/BibleClip/Bundle/ 로 모은다(git 에 넣지 않음 — 저장소 것을 그대로 쓴다).
# android/app/build.gradle.kts 의 RepoAssets 와 같은 일. CI 가 xcodegen 앞에서 돌린다.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
out="$here/BibleClip/Bundle"

rm -rf "$out"
mkdir -p "$out/web" "$out/android" "$out/ios" "$out/bible_versions" "$out/core"

# web/ — fonts.css 는 woff2 를 먼저 쓴다. otf/ttf 사본(약 17MB)은 뺀다.
rsync -a --exclude 'fonts/Pretendard-*.otf' --exclude 'fonts/Pretendard-*.ttf' --exclude 'README.md' \
  "$root/web/" "$out/web/"
cp "$root/android/app/src/main/assets/android/mobile.css" "$root/android/app/src/main/assets/android/mobile.js" "$out/android/"
cp "$here/BibleClip/bridge.js" "$here/BibleClip/ios.js" "$out/ios/"
cp "$root/android/app/src/main/assets/core/tables.json" "$out/core/"
# 기본 역본 — 저작권 역본은 넣지 않는다.
cp "$root/bible_versions/KRV.SQLite3" "$root/bible_versions/KJV+.SQLite3" "$out/bible_versions/"

du -sh "$out"
