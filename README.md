# DataPulse — 실시간 비즈니스 대시보드 SaaS

<p align="center">
  <strong>실시간 WebSocket 기반 비즈니스 메트릭 대시보드 SaaS 플랫폼</strong><br/>
  매출, 주문, 사용자, 전환율 등 핵심 KPI를 실시간으로 모니터링합니다.
</p>

## 주요 기능

### 핵심
- **멀티 대시보드** — 프로젝트/서비스별 독립 대시보드 생성
- **커스텀 메트릭** — 추적할 지표를 자유롭게 생성 (매출, 주문, 에러율 등)
- **실시간 WebSocket** — 차트/KPI/이벤트 피드 실시간 업데이트
- **JWT 인증** — 이메일 기반 로그인/회원가입

### 외부 연동
- **REST API** — API 키 발급 후 외부에서 데이터 전송 가능
- **Webhook** — 외부 시스템(쇼핑몰, 결제 등)에서 이벤트 수신
- **CSV 업로드** — 엑셀/CSV 데이터를 업로드하면 자동으로 메트릭 생성 + 차트화
- **임베드** — `<iframe>` 코드로 외부 사이트에 차트 삽입

### 모니터링
- **KPI 카드** — 현재 값 + 이전 대비 변화율
- **라인 차트** — 30일간 추이 (메트릭별)
- **실시간 이벤트 피드** — 주문/가입/환불 등 이벤트 스트리밍
- **알림 시스템** — 임계값 초과, 마일스톤 달성 자동 알림

## 데모 계정

```
이메일: demo@datapulse.io
비밀번호: demo1234
```

데모 계정에는 3개의 대시보드와 30일치 시뮬레이션 데이터가 포함되어 있습니다:
- 🛒 쇼핑몰 매출 현황 (매출, 주문, 가입, 전환율, 장바구니 포기율)
- 📢 마케팅 성과 분석 (광고 지출, 클릭수, 전환수, CPA)
- ⚙️ 서비스 운영 모니터링 (API 호출, 에러율, 응답시간, 활성 사용자)

## 기술스택

| 분류 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, WebSocket, asyncio |
| Database | SQLite (aiosqlite) |
| Frontend | HTML, Tailwind CSS, Chart.js |
| Auth | JWT (python-jose), SHA-256 |
| Real-time | WebSocket (서버 Push, 대시보드별 채널) |
| API | REST API + API Key 인증 |

## 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행 (데모 데이터 자동 생성)
python main.py

# 브라우저 접속
open http://localhost:8080
```

## API 사용법

### 1. API 키 발급
설정 → API 키 → 새 키 생성

### 2. 데이터 전송
```bash
curl -X POST http://localhost:8080/api/v1/push \
  -H "X-API-Key: dp_your_api_key" \
  -d "dashboard_id=1&metric_name=매출&value=150000"
```

### 3. 이벤트 전송
```bash
curl -X POST http://localhost:8080/api/v1/event \
  -H "X-API-Key: dp_your_api_key" \
  -d "dashboard_id=1&event_type=order&description=신규주문&amount=59000"
```

### 4. CSV 업로드
설정 → CSV 업로드 → 대시보드 선택 → 파일 선택
- 컬럼명이 자동으로 메트릭 이름이 됩니다
- `date`, `날짜` 컬럼은 시간으로 인식됩니다

### 5. 임베드
```html
<iframe src="http://localhost:8080/api/embed/YOUR_TOKEN" width="100%" height="400"></iframe>
```

## 아키텍처

```
External Systems
    │
    ├── REST API (X-API-Key 인증)
    ├── Webhook (URL 기반)
    └── CSV Upload
         │
    ┌────▼────┐
    │ FastAPI  │
    │  Server  │
    ├──────────┤
    │ JWT Auth │
    │ REST API │
    │ WebSocket│──── Push ────▶ Browser (Chart.js)
    │ Simulator│
    └────┬─────┘
         │
    ┌────▼────┐
    │  SQLite  │
    │ Database │
    └──────────┘
```

## 라이선스

MIT
