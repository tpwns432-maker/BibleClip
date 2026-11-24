# BibleClip 웹판 설치 안내 (서버 주인용)

두 사람이 성경을 읽고 감상을 나누는 비공개 사이트를 **집에 있는 리눅스 컴퓨터**에 설치합니다.
아래 명령을 차례로 복사해 붙여 넣으면 됩니다. 처음 설치는 15분 정도 걸립니다.

## 어떻게 생겼나
```
[내 폰 · PC] ──Tailscale(셋만의 사설 통로, https)──▶ [집 서버]  tailscale serve ─▶ BibleClip(127.0.0.1)
```
- BibleClip은 서버 **안에서만**(127.0.0.1) 열립니다. 공유기 포트를 열지 않고, 인터넷에도 드러나지 않습니다.
- 다른 기기는 **Tailscale**로만 들어옵니다. Tailscale에 연결된 기기(나와 초대한 사람)만 주소가 열립니다.
- 로그인해야 무엇이든 보입니다. 계정은 두 개, 회원가입은 없습니다.

| 위치 | 들어 있는 것 |
|---|---|
| `/opt/bibleclip` | 프로그램(GitHub에서 받은 그대로). 업데이트하면 바뀝니다. |
| `/var/lib/bibleclip` | **데이터** — 계정, 두 사람의 설정 · 노트 · 형광펜, 커뮤니티 글, 역본. **백업 대상** |
| `/etc/bibleclip/web.env` | 설정(포트, Tailscale 주소) |

## 준비물
- 리눅스(Ubuntu · Debian 권장, Fedora · Arch도 됨), 관리자 권한(`sudo`), 인터넷
- git: 없으면 `sudo apt install -y git` (Fedora: `sudo dnf install -y git`)

## 1. 프로그램 받기
```bash
sudo git clone https://github.com/tpwns432-maker/BibleClip.git /opt/bibleclip
```

## 2. 설치
```bash
sudo /opt/bibleclip/deploy/install.sh
```
하는 일을 화면에 1/6 ~ 6/6 으로 보여 줍니다.
1. Python 3.9 이상 확인(없으면 설치)
2. 전용 사용자 `bibleclip`(로그인 불가, 이 프로그램만 돌림)과 데이터 폴더
3. 가상환경 · 라이브러리(Flask, waitress)
4. 서비스 등록 — 꺼지면 다시 켜고, 서버를 다시 켜도 자동으로 켜집니다
5. **계정 만들기** — 아이디(영문 소문자), 화면에 보일 이름, 비밀번호(화면에 안 보임)를 두 번 물어봅니다.
   - 상대의 계정은 **임시 비밀번호**로 만들어 알려 주세요. 상대가 로그인한 뒤 홈 화면 아래
     **"비밀번호 바꾸기"**로 직접 바꿉니다(서버 주인도 모르는 비밀번호가 됩니다).
6. 시작 확인 — `✔ 켜졌습니다` 가 나오면 성공

## 3. 역본 넣기
개역한글과 원어 사전은 프로그램에 들어 있습니다. 개역개정 같은 다른 역본은 **저작권 때문에 GitHub에
없으므로** 가지고 계신 `.SQLite3` 파일을 직접 넣습니다.
```bash
sudo cp 개역개정.SQLite3 /var/lib/bibleclip/bible_versions/
sudo chown bibleclip: /var/lib/bibleclip/bible_versions/*
sudo systemctl restart bibleclip-web
```
(파일을 다른 컴퓨터에서 옮길 때는 USB나 `scp 파일 사용자@서버:~/` 로 서버에 먼저 가져온 뒤 위 명령.)

## 4. Tailscale로 연결하기
1. Tailscale 설치 · 로그인(처음 한 번):
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
   나오는 링크를 열어 Tailscale 계정으로 로그인합니다.
2. Tailscale 관리 화면 → **DNS** → **MagicDNS** 와 **HTTPS Certificates** 를 켭니다
   (https://login.tailscale.com/admin/dns).
3. BibleClip을 Tailscale 주소로 내보내기:
   ```bash
   sudo /opt/bibleclip/deploy/tailscale.sh
   ```
   마지막에 `주소: https://<서버이름>.<사설망>.ts.net` 이 나옵니다. 이 주소가 사이트입니다.
4. **상대에게 열어 주기**: 관리 화면 → **Machines** → 이 서버 옆 `…` → **Share…** → 상대의 이메일.
   상대는 자기 PC · 폰에 Tailscale 앱을 깔고, 받은 초대를 수락한 뒤 위 주소를 엽니다.
   (공유받은 사람은 이 서버 하나에만 들어올 수 있고, 서버 주인의 다른 기기는 보지 못합니다.)
   - 상대가 주소를 못 연다면: 관리 화면 → **Access controls** 를 바꾼 적이 있는지 확인하세요. 공유받은
     사람의 접속도 이 규칙을 따릅니다. 이 서버의 **443 포트**(https)만 열어 주면 됩니다.

## 업데이트
새 기능이 나오면:
```bash
sudo /opt/bibleclip/deploy/update.sh
```
새 코드를 받고(git pull) 라이브러리 · 서비스를 맞춘 뒤 다시 켭니다. 데이터는 그대로입니다.

## 백업 · 되돌리기
```bash
sudo /opt/bibleclip/deploy/backup.sh                 # ~/bibleclip-backup/bibleclip-날짜.tar.gz
sudo /opt/bibleclip/deploy/backup.sh --with-bibles   # 역본 파일까지(크기가 큼)
```
켜 둔 채로 해도 됩니다. 매주 자동으로 하려면 `sudo crontab -e` 에 한 줄:
```
0 4 * * 0  /opt/bibleclip/deploy/backup.sh /root/bibleclip-backup
```
백업 파일에는 비밀번호 해시와 로그인 열쇠가 들어 있으니 남에게 주지 마세요.

되돌리기(서버를 새로 깔았거나 데이터를 잃었을 때):
```bash
sudo systemctl stop bibleclip-web
sudo tar xzf bibleclip-날짜.tar.gz -C /var/lib/bibleclip
sudo chown -R bibleclip: /var/lib/bibleclip
sudo systemctl start bibleclip-web
```

## 계정 관리
```bash
cd /opt/bibleclip
A="sudo -u bibleclip .venv/bin/python -m bibleclip.server.accounts --data /var/lib/bibleclip"
$A list                       # 목록
$A add mina --name 미나        # 만들기
$A passwd sejun               # 비밀번호 다시 정하기(잊었을 때). 그 사람의 모든 로그인이 풀린다
$A remove mina                # 지우기(그 사람이 쓴 글 · 노트는 남는다)
```

## 문제가 생기면
```bash
systemctl status bibleclip-web            # 켜져 있나
journalctl -u bibleclip-web -n 50         # 최근 기록
sudo systemctl restart bibleclip-web      # 다시 켜기
tailscale serve status                    # Tailscale 내보내기 상태
```
- **주소가 안 열림**: 그 기기에서 Tailscale 앱이 켜져(연결됨) 있는지, 서버가 켜져 있는지 확인.
- **"아이디나 비밀번호가 맞지 않습니다"가 계속**: 15분 안에 5번 틀리면 15분 동안 막힙니다. 기다리거나 위 `passwd`.
- **역본이 안 보임**: 파일을 넣은 뒤 `sudo systemctl restart bibleclip-web` 했는지, 파일 주인이 `bibleclip` 인지.

## 지우기
```bash
sudo systemctl disable --now bibleclip-web
sudo tailscale serve reset
sudo rm /etc/systemd/system/bibleclip-web.service && sudo systemctl daemon-reload
sudo rm -rf /opt/bibleclip /etc/bibleclip
# 데이터까지 지우려면(되돌릴 수 없음):  sudo rm -rf /var/lib/bibleclip && sudo userdel bibleclip
```

## 직접 실행(systemd 없이, 시험용)
```bash
cd /opt/bibleclip && python3 -m venv .venv && .venv/bin/pip install -r requirements-server.txt
.venv/bin/python -m bibleclip.server.accounts --data ~/bibleclip-data add <아이디> --name <이름>
.venv/bin/python -m bibleclip.server --data ~/bibleclip-data      # http://127.0.0.1:8765
```
