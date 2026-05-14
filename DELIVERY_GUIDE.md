# 기획자 전달 가이드

## Mac 전달물

Mac 사용자에게는 아래 파일을 전달합니다.

```text
JobPostingCollector-mac.zip
```

압축을 풀면 `JobPostingCollector.app`이 나옵니다. 더블클릭해서 실행하면 됩니다.
앱은 macOS 기본 대화상자로 사이트, URL, 저장 폴더를 물어보고 수집을 실행합니다. 터미널 명령어 입력은 필요 없습니다.

최초 실행 시 macOS 보안 경고가 뜨면:

```text
JobPostingCollector.app 우클릭 > 열기 > 열기
```

상대방 Mac에 Python 3이 없으면 앱이 안내창을 띄웁니다. 이 경우 개발자에게 Python 3 설치 또는 독립 실행형 빌드를 요청해야 합니다.

## Windows 전달물

Windows용 실행 파일은 Windows PC에서 한 번 빌드해야 합니다. Windows PC에서 이 프로젝트 폴더를 열고 아래 파일을 더블클릭합니다.

```text
build_windows.bat
```

빌드가 끝나면 아래 폴더가 생깁니다.

```text
dist\JobPostingCollector\
```

Windows 사용자에게는 이 `JobPostingCollector` 폴더를 압축해서 전달합니다. 압축을 푼 뒤 `JobPostingCollector.exe`를 더블클릭하면 됩니다.

SmartScreen 경고가 뜨면:

```text
추가 정보 > 실행
```

## 빌드 담당자용

Mac 앱을 다시 만들 때:

```text
build_mac.command
```

Windows 앱을 만들 때:

```text
build_windows.bat
```

빌드 담당자 컴퓨터에는 Python 3이 필요합니다. 기획자 컴퓨터에는 Python 설치가 필요 없습니다.
