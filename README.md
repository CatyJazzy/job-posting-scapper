# 공고 파일 수집기

Jobda와 인디스워크의 공고 이미지/PDF를 자동 저장하는 작은 수집기입니다. 서버나 브라우저 확장프로그램 없이 Python 표준 라이브러리만 사용합니다.

## 기획자용 앱 실행

Mac은 `JobPostingCollector.app`, Windows는 `JobPostingCollector.exe` 형태로 전달하는 것을 권장합니다. Mac 앱은 macOS 기본 대화상자로 사이트, URL, 저장 폴더를 물어보고 수집을 실행합니다.

배포 파일을 만드는 방법은 `DELIVERY_GUIDE.md`를 참고하세요.

## 기획자용 실행

Windows:

```bat
run_windows.bat
```

Mac:

```sh
run_mac.command
```

실행 후 메뉴에서 `Jobda`, `인디스워크`, `둘 다` 중 하나를 선택하면 `collected` 폴더 아래에 결과가 저장됩니다.
저장 폴더 입력에서 그냥 Enter를 누르면 기본값 `collected`를 사용합니다.
Jobda를 선택하면 URL 입력 단계가 나오며, 그냥 Enter를 누르면 기본값 `https://www.jobda.im/position`을 사용합니다. Jobda 상세 공고 URL을 넣으면 해당 공고 하나만 수집합니다.
인디스워크를 선택하면 URL 입력 단계가 한 번 더 나오며, 그냥 Enter를 누르면 기본값 `https://inthiswork.com/entry`를 사용합니다.

## 개발자용 실행

```sh
python3 collect_notices.py --site both --limit 40 --out collected
python3 collect_notices.py --site jobda --limit 60 --out collected
python3 collect_notices.py --site jobda --jobda-url https://www.jobda.im/position --limit 60 --out collected
python3 collect_notices.py --site inthiswork --inthiswork-url https://inthiswork.com/entry --limit 40 --out collected
python3 collect_notices.py --site inthiswork --detail-limit 5 --limit 40 --out collected
```

인디스워크는 목록 카드 이미지를 저장하지 않습니다. 목록은 상세 페이지 URL을 찾는 용도로만 쓰고, `/archives/{id}` 상세 페이지 본문 안의 공고 이미지/PDF만 저장합니다. `--detail-limit`은 상세 페이지를 몇 개까지 열지 제한하고, 기본값 `0`은 `--limit` 대상 전체를 처리한다는 뜻입니다.
Jobda는 상세 API의 `jobDescription` 본문 HTML 안에 있는 공고 이미지/PDF만 저장합니다. API의 보조 이미지, 썸네일, 회사 로고는 저장하지 않습니다.
작은 로고/아이콘으로 보이는 이미지는 다운로드 직전에 크기를 확인해 `skipped` 처리하고 저장하지 않습니다. 인디스워크 상세 본문 이미지도 너무 작은 보조 이미지는 저장하지 않습니다.

## 결과 구조

```text
collected/
  jobda_20260514_143000/
    manifest.json
    jobda_20260514_143000_001_공고명.jpg
  inthiswork_20260514_143100/
    manifest.json
    inthiswork_20260514_143100_001_공고명.png
```

`manifest.json`에는 공고 URL, 원본 파일 URL, 저장 성공/실패 상태가 기록됩니다.
