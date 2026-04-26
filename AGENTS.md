# Codex 작업 지침

이 프로젝트는 카카오톡 업무보고서 생성 웹서비스입니다.

## 목표

카카오톡 단톡방 대화 내보내기 파일을 업로드하면 기간별 시설관리 업무보고서를 생성합니다.

## 기술 스택

- frontend: Next.js, TypeScript, Tailwind CSS
- backend: FastAPI, Python 3.12
- AI: OpenAI Chat Completions
- local dev: Docker Compose

## 개발 원칙

- 모바일 우선 UI를 유지합니다.
- 카카오톡 원본 대화는 서버에 저장하지 않는 방향을 기본값으로 합니다.
- 개인정보가 노출될 수 있으므로 로그에 원문 전체를 남기지 않습니다.
- 기능은 PR 단위로 작게 나눕니다.
- 보고서 생성 결과는 사실/추정을 구분합니다.

## 검증 명령

```bash
cd backend && python -m compileall app
cd frontend && npm run build
```
