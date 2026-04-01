import asyncio
import random
import json
from datetime import datetime
from models import get_db

# 실시간 데이터를 받을 WebSocket 클라이언트들
connected_clients: set = set()

# 시뮬레이션 상태
state = {
    "revenue": 0,
    "orders": 0,
    "users": 0,
    "conversion": 0,
}

PRODUCTS = ["프리미엄 플랜", "스타터 플랜", "엔터프라이즈", "API 크레딧", "데이터 분석 리포트", "커스텀 대시보드"]
CITIES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "제주"]
EVENT_TYPES = ["order", "signup", "upgrade", "refund", "alert"]

async def broadcast(data: dict):
    if connected_clients:
        msg = json.dumps(data, ensure_ascii=False)
        dead = set()
        for ws in connected_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        connected_clients -= dead

async def generate_event():
    """랜덤 비즈니스 이벤트 생성"""
    etype = random.choice(EVENT_TYPES)

    if etype == "order":
        product = random.choice(PRODUCTS)
        amount = random.choice([29000, 59000, 99000, 199000, 499000])
        city = random.choice(CITIES)
        desc = f"{city}에서 {product} 주문"
        state["revenue"] += amount
        state["orders"] += 1
    elif etype == "signup":
        city = random.choice(CITIES)
        desc = f"{city}에서 신규 가입"
        amount = 0
        state["users"] += 1
    elif etype == "upgrade":
        product = random.choice(PRODUCTS[:3])
        amount = random.choice([30000, 70000, 100000])
        desc = f"{product}으로 업그레이드"
        state["revenue"] += amount
    elif etype == "refund":
        amount = -random.choice([29000, 59000])
        desc = "환불 처리"
        state["revenue"] += amount
    else:
        amount = 0
        desc = "시스템 점검 알림"

    state["conversion"] = round(random.uniform(2.1, 5.8), 1)

    # DB 저장
    db = await get_db()
    await db.execute(
        "INSERT INTO events (event_type, description, amount) VALUES (?,?,?)",
        (etype, desc, amount)
    )

    # 메트릭 저장
    for mt, val in state.items():
        await db.execute(
            "INSERT INTO metrics (metric_type, value) VALUES (?,?)",
            (mt, val)
        )

    # 알림 생성 (매출 급등)
    if state["revenue"] > 0 and state["orders"] % 10 == 0:
        await db.execute(
            "INSERT INTO alerts (title, message, severity) VALUES (?,?,?)",
            ("주문 마일스톤", f"누적 {state['orders']}건 달성! 🎉", "success")
        )

    await db.commit()
    await db.close()

    # WebSocket 브로드캐스트
    await broadcast({
        "type": "update",
        "kpi": state,
        "event": {
            "type": etype,
            "description": desc,
            "amount": amount,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
    })

async def run_simulator():
    """백그라운드에서 1~3초마다 이벤트 생성"""
    while True:
        await generate_event()
        await asyncio.sleep(random.uniform(1, 3))
