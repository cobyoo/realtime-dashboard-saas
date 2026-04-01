# DataPulse — 실시간 비즈니스 대시보드 SaaS

실시간 WebSocket 기반 비즈니스 메트릭 대시보드입니다.
매출, 주문, 사용자, 전환율 등 핵심 KPI를 실시간으로 모니터링할 수 있습니다.

## 주요 기능

- **실시간 KPI 카드** — 매출, 주문, 사용자, 전환율 실시간 업데이트
- **라이브 차트** — 매출/주문/사용자 추이 라인 차트 + 이벤트 분포 도넛 차트
- **실시간 이벤트 피드** — 주문, 가입, 업그레이드, 환불 이벤트 실시간 스트리밍
- **알림 시스템** — 마일스톤 달성 등 자동 알림
- **인증** — JWT 기반 로그인/회원가입
- **데모 시뮬레이터** — 자동으로 비즈니스 데이터를 생성하여 대시보드 시연

## 기술스택

| 분류 | 기술 |
|------|------|
| Backend | Python, FastAPI, WebSocket |
| Database | SQLite (aiosqlite) |
| Frontend | HTML, Tailwind CSS, Chart.js |
| Auth | JWT (python-jose), bcrypt |
| Real-time | WebSocket (서버 Push) |

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 서버 실행
python main.py

# 3. 브라우저 접속
open http://localhost:8080
```

## 스크린샷

### 로그인
- 이메일/비밀번호 기반 JWT 인증
- 회원가입/로그인 전환

### 대시보드
- 4개의 KPI 카드 (실시간 업데이트)
- 4개의 차트 (매출 추이, 주문 추이, 사용자 추이, 이벤트 분포)
- 실시간 이벤트 피드
- 알림 벨

## 아키텍처

```
Client (Browser)
    ↕ WebSocket
FastAPI Server
    ├── JWT Auth
    ├── REST API (KPI, Events, Alerts, Charts)
    ├── WebSocket Hub (실시간 Push)
    └── Simulator (데모 데이터 생성)
         ↕
      SQLite DB
```

## 라이선스

MIT
