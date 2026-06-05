# Build the BibleClip web UI (pywebview) into a frozen onedir app on Windows.
#
#   powershell -File packaging\build_web.ps1
#   (if blocked by execution policy, run the PyInstaller line below directly)
#
# ⚠️ 이 파일은 반드시 UTF-8 "BOM 포함"으로 저장할 것. Windows PowerShell 5.1은
#    BOM 없는 .ps1을 시스템 ANSI 코드페이지로 읽어 한글 파일명("사용법"·"개역한글S")
#    리터럴을 깨뜨려 Copy-Item이 조용히 실패함(파일 누락). BOM이 있으면 PS5.1/PS7
#    모두 UTF-8로 정확히 읽음. (편집 도구가 BOM을 떼면 한글 복사가 다시 깨짐.)
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
  Write-Host "node not found - skipping JS syntax check" -ForegroundColor Yellow
}

# ⚠️ kiwipiepy(형태소 검색기)는 프로즌 빌드에서 제외한다. kiwipiepy 의 C++ 네이티브
# 런타임이 PyInstaller 로 동봉된 pywebview(pythonnet/WebView2)와 같은 프로세스에서
# 공존하면 네이티브 힙 손상(0xC0000374)으로 앱이 즉시 강제 종료된다(검증됨). 따라서
# 배포본은 형태소 검색을 끄고 trigram 폴백만 사용(morph._get_kiwi 가 sys.frozen 에서
# None 반환). kiwipiepy 를 제외하지 않으면 morph 의 import 를 따라가 kiwipiepy +
# torch/transformers 등 거대 ML 스택까지 끌어와 ~1GB 로 폭증하므로 반드시 제외.
# 형태소 검색은 소스/개발 실행에서만 동작.
$kiwiExclude = @(
  'kiwipiepy','kiwipiepy_model',
  'torch','transformers','cv2','scipy','sklearn','numba','llvmlite','pandas',
  'matplotlib','PIL','tokenizers','numpy','lxml','safetensors','huggingface_hub',
  'sympy','networkx'
) | ForEach-Object { '--exclude-module', $_ }

python -m PyInstaller --onedir --windowed --noconfirm --clean `
  --collect-submodules bibleclip `
  --hidden-import pyperclip `
  @kiwiExclude `
  --add-data "web;web" `
  --icon=icon.ico --name BibleClipWeb `
  --distpath dist_web --workpath build_web `
  bibleclip_web.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Runtime data lives next to the exe (config.get_base_dir() = exe dir when frozen).
$dst = "dist_web\BibleClipWeb"
Copy-Item icon.ico $dst -Force
Copy-Item 사용법.txt, 사용법.html, 사용법.css, 사용법.js, version_changes.json $dst -Force
# Copyright guard: bundle ONLY copyright-clean data - KRV(개역한글, royalty-free)
# and 개역한글S(KRV+Strong tags). Other bibles (ESV/NKJV/...) and the lexicons
# (HebGrkKo TWOT-Korean, HebGrkEn) are user-supplied modules, never redistributed.
New-Item -ItemType Directory -Force "$dst\bible_versions" | Out-Null
Copy-Item bible_versions\KRV.SQLite3 "$dst\bible_versions\" -Force
New-Item -ItemType Directory -Force "$dst\original_lang" | Out-Null
Copy-Item "original_lang\개역한글S.sdb" "$dst\original_lang\" -Force

# 동봉 검증: 한글 파일명이 PS5.1에서 깨져 누락되는 회귀를 빌드 단계에서 즉시 포착.
$must = @("$dst\사용법.html","$dst\사용법.css","$dst\사용법.js",
          "$dst\original_lang\개역한글S.sdb","$dst\bible_versions\KRV.SQLite3")
foreach ($p in $must) {
  if (-not (Test-Path -LiteralPath $p)) { throw "필수 동봉 파일 누락: $p (한글 파일명 인코딩/ BOM 확인)" }
}
Write-Host "필수 동봉 파일 확인 완료" -ForegroundColor Green

Write-Host "`nBuilt: $dst\BibleClipWeb.exe" -ForegroundColor Green
