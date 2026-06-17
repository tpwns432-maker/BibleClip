# Bundled reading fonts (기본 동봉 읽기 글꼴)

설정 ▸ 읽기 ▸ 읽기 글꼴 메뉴에 **기본으로 노출되는** 본문용 한국어 글꼴.
`web/` 폴더가 `--add-data "web;web"` 로 통째로 동봉되므로(빌드 스크립트 추가 수정
불필요), 이 폴더의 글꼴이 모든 플랫폼 빌드에 자동으로 포함된다.

- **나눔고딕.ttf** — NanumGothic Regular (산세리프)
- **나눔명조.ttf** — NanumMyeongjo Regular (세리프/명조)
- **라이선스**: SIL Open Font License 1.1 (`OFL.txt`). 임베드·재배포 자유.
- **출처**: Google Fonts (Naver / Sandoll, OFL)
  - https://github.com/google/fonts/tree/main/ofl/nanumgothic
  - https://github.com/google/fonts/tree/main/ofl/nanummyeongjo

## 메뉴 라벨 = 파일명
`list_fonts` 가 파일명(확장자 제외)을 그대로 글꼴 family/라벨로 쓴다. 그래서 한글
파일명이 곧 한글 메뉴 라벨(`나눔고딕`/`나눔명조`)이 된다. 글꼴을 더 추가하려면 원하는
표시 이름으로 .ttf/.otf 파일을 이 폴더에 두면 된다(백엔드 `_builtin_fonts_dir`).

> 사용자가 직접 넣는 글꼴은 데이터 폴더의 `fonts/` 폴더에 둔다(이 번들과 별개, 메뉴에
> 이어서 표시됨). 동봉 글꼴이 같은 이름이면 동봉본이 우선한다.
