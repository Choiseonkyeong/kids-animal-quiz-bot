# 동글동글 동물원 퀴즈 숏츠 생성기

이 프로그램은 4~7세 아이들을 위한 동물 퀴즈 유튜브 숏츠(1080x1920, 40~55초)를 자동으로 만듭니다.

동작 순서: 대본 생성(Claude) → 음성(Google TTS) → 이미지(gpt-image-1 또는 로컬 파일) → 렌더링(MoviePy) → (선택) YouTube 업로드

## 설치

Python 3.11 이상과 ffmpeg가 필요합니다. ffmpeg는 MoviePy가 쓰는 imageio-ffmpeg에 포함되어 있습니다.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

테스트까지 돌리려면 `requirements.txt` 대신 `requirements-dev.txt`를 설치하세요.

| 패키지 | 쓰는 이유 |
|---|---|
| anthropic | Claude API로 대본 생성 |
| moviepy | 영상·오디오 합성 (Pillow, numpy 포함) |
| python-dotenv | `.env`에서 API 키 로드 |
| google-api-python-client, google-auth-oauthlib | YouTube 업로드와 OAuth 인증 |

Google TTS와 OpenAI 이미지 API는 추가 SDK 없이 표준 라이브러리(urllib)로 호출합니다.

## .env 설정

```bash
cp .env.example .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | O | Claude API 키 |
| `GOOGLE_TTS_API_KEY` | O | Google Cloud 콘솔에서 Text-to-Speech API를 켜고 발급한 API 키 |
| `OPENAI_API_KEY` | X | 이미지 생성용. 비워 두면 `assets/images/`의 이미지만 쓰고, 이미지가 없으면 물음표 화면으로 대신합니다 |
| `YOUTUBE_PRIVACY_STATUS` | X | `private`(기본), `unlisted`, `public` |

YouTube에 업로드하려면 Google Cloud 콘솔에서 YouTube Data API v3를 켜고, OAuth 클라이언트(데스크톱 앱)를 만들어 `client_secret.json`으로 프로젝트 루트에 저장하세요. 첫 업로드 때 브라우저 인증을 한 번 거치면 `token.json`이 저장되고, 그다음부터는 바로 업로드됩니다.

## assets 폴더 준비

> 동물 소리, BGM, 효과음은 **CC0 같은 무료 라이선스 파일만** 쓰세요 (예: freesound.org의 CC0 필터, Pixabay Sound Effects). 출처와 라이선스는 따로 기록해 두세요.

```
assets/
├─ fonts/NanumSquareRoundEB.ttf   # 필수. 네이버 나눔스퀘어라운드 (OFL, 상업 이용 무료)
├─ sounds/{동물}.mp3              # sound 시리즈용. 파일 이름은 한국어 동물 이름 (예: 소.mp3, 오리.mp3)
├─ bgm/*.mp3                      # 선택. 여러 개면 무작위로 하나를 골라 낮은 볼륨으로 깝니다
├─ sfx/countdown.mp3, reveal.mp3  # 선택. 없으면 기본 '띵'·'짠' 소리를 자동으로 만듭니다
├─ images/{이름}.png              # 선택. 동물 이름이나 정답 이름으로 넣으면 생성 대신 이 파일을 씁니다
└─ logo.png                       # 선택. 화면 왼쪽 위에 작게 표시됩니다
```

- 폰트는 [네이버 한글한글 아름답게](https://hangeul.naver.com/font)에서 받습니다.
- sound 시리즈는 `assets/sounds/`에 있는 동물로만 대본을 만듭니다. 소리 파일이 3개 이상 있어야 하고, 넉넉하게 10개 이상 준비하길 권장합니다.
- 생성한 이미지와 TTS는 `assets/cache/`에 저장되어 같은 문장이나 같은 그림을 다시 만들지 않습니다.

## 실행

```bash
python main.py --series sound
```

```bash
python main.py --series baby --count 3
```

```bash
python main.py --series food --upload
```

- `--series`: `sound`(누구 소리일까?), `footprint`(누구 발자국일까?), `baby`(아기 이름은?), `count`(동물이랑 숫자·색깔), `food`(뭐 먹고 살까?)
- `--count N`: 만들 편 수 (기본 1)
- `--upload`: 지정했을 때만 업로드합니다. 공개 상태는 `YOUTUBE_PRIVACY_STATUS`를 따르고, 아동용(`selfDeclaredMadeForKids`)으로 설정됩니다.

결과물은 `output/{series}/{YYYYMMDD}_{NN}/`에 저장됩니다: `video.mp4`, `script.json`, `thumbnail.png`.
사용한 동물은 `data/history.json`에 기록되고, 다음 편 프롬프트의 제외 목록으로 들어갑니다.

## 영상 구성

[훅 3초] → [퀴즈 × 4~5: 질문 → 3·2·1 카운트다운(3초, 나레이션 없음) → 정답 공개] → [아웃트로 3~5초]

- 55초를 넘으면 뒤쪽 퀴즈부터 뺍니다. 40초보다 짧으면 정답 공개 구간과 아웃트로를 늘립니다.
- 자막은 핵심 단어(질문 키워드, 정답)만 크게 보여 줍니다.

## 설정 바꾸기

`config.py`의 dataclass에서 채널명, TTS 음성·속도, 폰트 크기, 배경 팔레트, 이미지 스타일 키워드, 금지어, 영상 길이를 바꿀 수 있습니다.
프롬프트는 `prompts/system.md`(공통)와 `prompts/series/*.md`(시리즈별)에 있습니다.

## 테스트

```bash
python -m pytest -q
```

`tests/test_pipeline_smoke.py`는 외부 API 대신 가짜 대본·TTS·이미지로 렌더링까지 전체 흐름을 실행합니다. 폰트 파일이 없으면 이 테스트는 건너뜁니다.
