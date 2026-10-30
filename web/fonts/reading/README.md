# Bundled reading fonts (기본 동봉 읽기 글꼴)

설정 ▸ 읽기 ▸ 읽기 글꼴 메뉴에 **기본으로 노출되는** 본문용 한국어 글꼴.
`web/` 폴더가 `--add-data "web;web"` 로 통째로 동봉되므로(빌드 스크립트 추가 수정
불필요), 이 폴더의 글꼴이 모든 플랫폼 빌드에 자동으로 포함된다.

- **NanumGothic.ttf** — 나눔고딕 Regular (산세리프)
- **NanumMyeongjo.ttf** — 나눔명조 Regular (세리프/명조)
- **라이선스**: SIL Open Font License 1.1 (`OFL.txt`). 임베드·재배포 자유.
- **출처**: Google Fonts (Naver / Sandoll, OFL)
  - https://github.com/google/fonts/tree/main/ofl/nanumgothic
  - https://github.com/google/fonts/tree/main/ofl/nanummyeongjo

## 메뉴 라벨 = 파일명 (동봉 글꼴만 예외)
`list_fonts` 가 파일명(확장자 제외)을 그대로 글꼴 family/라벨로 쓴다. 단 **이 폴더의
파일 이름은 반드시 영문**이다(v1.2.1). 맥 .app 안의 한글 파일 이름은 Finder 로 복사될 때
NFD 로 바뀌어 서명이 깨진다("손상됨"). 그래서 동봉 글꼴은 영문 파일명 + 한글 라벨 대응표
(`SystemRoutes._BUILTIN_FAMILY`: `NanumGothic`→`나눔고딕`)로 메뉴와 저장값(`reading_font`)을
예전과 같게 유지한다. 글꼴을 더 동봉하려면 영문 파일명으로 넣고 대응표에 한 줄 추가한다.
CI 맥 빌드는 .app 안에 영문이 아닌 파일 이름이 있으면 실패한다.

> 사용자가 직접 넣는 글꼴은 데이터 폴더의 `fonts/` 폴더에 둔다(이 번들과 별개, 메뉴에
> 이어서 표시됨). 동봉 글꼴이 같은 이름이면 동봉본이 우선한다.
