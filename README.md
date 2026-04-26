# Facility Report System

카카오톡 특정 단톡방의 기간별 대화 내용을 시설관리 업무보고서로 변환하는 독립 웹서비스입니다.

## 주요 기능

- 카카오톡 대화 내보내기 `.txt` 업로드
- 시작일/종료일 기준 기간 필터링
- 업무, 담당자, 완료/미완료, 주요 이슈 자동 정리
- 보고서 복사 후 관리사무소 문서에 붙여넣기
- 스마트폰 브라우저에서 사용 가능한 모바일 우선 UI

## 실행 방법

### 1. 로컬 개발 환경 준비

Windows PowerShell:

```powershell
pwsh -File scripts\setup.ps1
```

`backend/.env`에 OpenAI API 키를 입력합니다.

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
ALLOWED_ORIGINS=http://localhost:3000
```

API 키가 없으면 규칙 기반 임시 보고서가 생성됩니다.

### 2. 로컬 개발 실행

Backend:

```powershell
pwsh -File scripts\dev-backend.ps1 -Reload
```

Frontend:

```powershell
pwsh -File scripts\dev-frontend.ps1
```

접속:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health

검증:

```powershell
pwsh -File scripts\check.ps1
```

### 3. 폰 원격개발: GitHub Codespaces

폰에서 코드를 수정하고 바로 실행 확인까지 하려면 GitHub Codespaces를 사용합니다.

1. 이 프로젝트를 단독 GitHub 저장소로 올립니다.
2. 폰 브라우저에서 GitHub 저장소를 엽니다.
3. `Code` > `Codespaces` > `Create codespace`를 선택합니다.
4. Codespaces가 열리면 `.devcontainer/devcontainer.json` 설정으로 의존성이 자동 설치되고 개발 서버가 자동 실행됩니다.
5. Ports 패널에서 `Frontend` 또는 포트 `3000`을 엽니다.

Codespaces에서 자동 실행되는 서버:

```text
Frontend: 3000
Backend API: 8000
```

수동으로 다시 실행해야 할 때:

```bash
bash scripts/codespaces-start.sh
```

또는 터미널 2개에서 각각 실행:

```bash
bash scripts/dev-backend.sh
bash scripts/dev-frontend.sh
```

Codespaces에서는 프론트가 `*.app.github.dev` 주소를 감지해 백엔드 `8000` 포트 주소를 자동으로 계산합니다. 백엔드 CORS도 `*.app.github.dev`를 허용하도록 기본 설정되어 있습니다.

### 4. Render로 폰 테스트/배포

Render는 개발 IDE가 아니라 배포 서버입니다. 원격개발 흐름은 다음처럼 가져갑니다.

```text
폰 Codespaces에서 수정 → git commit/push → Render 자동 배포 → 폰에서 Render 주소로 테스트
```

이 폴더의 `render.yaml`은 아래 서비스 이름을 기준으로 작성되어 있습니다.

- Backend: `facility-report-backend`
- Frontend: `facility-report-frontend`

Render Blueprint를 쓰거나 수동으로 만들 때 설정은 다음과 같습니다.

Backend:

```text
Root Directory: backend
Runtime: Docker
Environment Variables:
  OPENAI_API_KEY=<선택>
  OPENAI_MODEL=gpt-5.5
  ALLOWED_ORIGINS=https://facility-report-frontend.onrender.com
  ALLOWED_ORIGIN_REGEX=https://.*\.app\.github\.dev
```

Frontend:

```text
Root Directory: frontend
Runtime: Docker
Environment Variables:
  NEXT_PUBLIC_API_BASE=https://facility-report-backend.onrender.com
```

배포 후 폰에서 접속:

```text
https://facility-report-frontend.onrender.com
```

서비스 이름을 다르게 만들면 `ALLOWED_ORIGINS`와 `NEXT_PUBLIC_API_BASE`도 실제 Render 주소에 맞춰 바꿔야 합니다.

### 5. Docker로 실행

```bash
docker compose up --build
```

접속:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health

## 카카오톡 대화 내보내기

1. 카카오톡 단톡방 열기
2. 설정
3. 대화 내용 내보내기
4. 텍스트 파일 저장
5. 웹서비스에서 파일 업로드
6. 기간 선택 후 보고서 생성

## 개인정보 주의

- 실제 입주민 연락처, 차량번호, 민감정보가 포함될 수 있습니다.
- 운영 배포 전 접근 권한, HTTPS, 로그 마스킹, 파일 자동삭제 정책을 추가해야 합니다.
- 대화 원본 파일은 장기 보관하지 않는 방향을 권장합니다.

## 향후 확장

- Word/PDF 보고서 다운로드
- 담당자별 월간 업무 통계
- 반복 민원/위험 키워드 알림
- Google Drive 보고서 저장
