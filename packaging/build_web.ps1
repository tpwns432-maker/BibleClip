# Build the BibleClip web UI (pywebview) into a frozen onedir app on Windows.
#
#   powershell -File packaging\build_web.ps1
#   (if blocked by execution policy, run the PyInstaller line below directly)
#
# Output: dist_web\BibleClipWeb\BibleClipWeb.exe (+ bible_versions, original_lang
# copied next to it). The web/ folder (HTML/CSS/JS + Pretendard fonts) is bundled
# INSIDE the exe via --add-data, resolved at runtime by config.get_resource_dir().
# pywebview ships its own PyInstaller hook, so the WebView2/pythonnet backend is
# collected automatically; no extra --collect flags needed for it.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)   # repo root

# 9차 모듈화: 분할된 web/**/*.js 를 빌드 전에 node --check 로 문법 검증
# (core/cards/search-notes 중 하나라도 깨지면 빌드 중단). node 부재 시 건너뜀.
if (Get-Command node -ErrorAction SilentlyContinue) {
  $jsFiles = Get-ChildItem -Recurse web -Filter *.js
  foreach ($js in $jsFiles) {
    & node --check $js.FullName
    if ($LASTEXITCODE -ne 0) { throw "node --check failed: $($js.FullName)" }
  }
  Write-Host "web/**/*.js syntax OK ($($jsFiles.Count) files)" -ForegroundColor Green
} else {
  Write-Host "node not found — skipping JS syntax check" -ForegroundColor Yellow
}

# --collect-all kiwipiepy(+model): 한국어 형태소 검색기(9차 Phase 2)의 C 확장과
# 모델 데이터를 동봉. 미동봉 시 앱은 trigram 폴백으로 동작하나, 동봉해야 검색창
# 형태소 분석이 배포본에서 활성화됨. (모델이 수십 MB — 빌드 용량 증가 유의)
python -m PyInstaller --onedir --windowed --noconfirm --clean `
  --collect-submodules bibleclip `
  --hidden-import pyperclip `
  --collect-all kiwipiepy --collect-all kiwipiepy_model `
  --add-data "web;web" `
  --icon=icon.ico --name BibleClipWeb `
  --distpath dist_web --workpath build_web `
  bibleclip_web.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Runtime data lives next to the exe (config.get_base_dir() = exe dir when frozen).
$dst = "dist_web\BibleClipWeb"
Copy-Item icon.ico $dst -Force
Copy-Item 사용법.txt, 사용법.html, 사용법.css, 사용법.js, version_changes.json $dst -Force
# Copyright guard: bundle ONLY copyright-clean data — KRV(개역한글, royalty-free)
# and 개역한글S(KRV+Strong tags). Other bibles (ESV/NKJV/…) and the lexicons
# (HebGrkKo TWOT-Korean, HebGrkEn) are user-supplied modules, never redistributed.
New-Item -ItemType Directory -Force "$dst\bible_versions" | Out-Null
Copy-Item bible_versions\KRV.SQLite3 "$dst\bible_versions\" -Force
New-Item -ItemType Directory -Force "$dst\original_lang" | Out-Null
Copy-Item "original_lang\개역한글S.sdb" "$dst\original_lang\" -Force

Write-Host "`nBuilt: $dst\BibleClipWeb.exe" -ForegroundColor Green
