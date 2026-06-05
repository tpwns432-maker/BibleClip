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

python -m PyInstaller --onedir --windowed --noconfirm --clean `
  --collect-submodules bibleclip `
  --hidden-import pyperclip `
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
