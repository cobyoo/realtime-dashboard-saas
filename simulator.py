import asyncio
import random
import json
from datetime import datetime, timedelta
from models import get_db, gen_api_key

connected_clients: dict = {}  # dashboard_id -> set of websockets

PRODUCTS = ["프리미엄 플랜", "스타터 플랜", "엔터프라이즈", "API 크레딧", "데이터 리포트", "커스텀 위젯"]
CITIES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "제주", "수원", "고양"]
NAMES = ["김민수", "이지은", "박서준", "최유진", "정하늘", "강도현", "윤서아", "임재현", "한소희", "오준혁"]

async def broadcast(dashboard_id: int, data: dict):
    clients = connected_clients.get(dashboard_id, set())
    if not clients:
        return
    msg = json.dumps(data, ensure_ascii=False)
    dead = set()
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    clients -= dead

async def seed_demo_data():
    """데모 데이터 시드 — 회원가입 + 대시보드 + 30일치 데이터"""
    db = await get_db()

    # 이미 데모 유저가 있으면 스킵
    existing = await (await db.execute("SELECT id FROM users WHERE email='demo@datapulse.io'")).fetchone()
    if existing:
        await db.close()
        return existing["id"]

    from auth import hash_password

    # 데모 유저
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash, company) VALUES (?,?,?)",
        ("demo@datapulse.io", hash_password("demo1234"), "DataPulse Inc.")
    )
    user_id = cursor.lastrowid

    # API 키
    await db.execute(
        "INSERT INTO api_keys (user_id, key, name) VALUES (?,?,?)",
        (user_id, gen_api_key(), "Production Key")
    )
    await db.execute(
        "INSERT INTO api_keys (user_id, key, name) VALUES (?,?,?)",
        (user_id, gen_api_key(), "Development Key")
    )

    # 대시보드 3개
    dashboards = [
        ("쇼핑몰 매출 현황", "온라인 쇼핑몰 실시간 매출 및 주문 모니터링"),
        ("마케팅 성과 분석", "광고 캠페인별 성과 및 전환율 추적"),
        ("서비스 운영 모니터링", "API 호출량, 에러율, 응답시간 모니터링"),
    ]
    dash_ids = []
    for name, desc in dashboards:
        import uuid
        cursor = await db.execute(
            "INSERT INTO dashboards (user_id, name, description, embed_token) VALUES (?,?,?,?)",
            (user_id, name, desc, uuid.uuid4().hex[:16])
        )
        dash_ids.append(cursor.lastrowid)

    # 대시보드 1: 쇼핑몰 — 커스텀 메트릭
    shop_metrics = [
        ("일 매출", "원", "#34d399"),
        ("주문 수", "건", "#60a5fa"),
        ("회원가입", "명", "#a78bfa"),
        ("전환율", "%", "#fbbf24"),
        ("장바구니 포기율", "%", "#f87171"),
    ]
    shop_metric_ids = []
    for name, unit, color in shop_metrics:
        cursor = await db.execute(
            "INSERT INTO custom_metrics (dashboard_id, name, unit, color) VALUES (?,?,?,?)",
            (dash_ids[0], name, unit, color)
        )
        shop_metric_ids.append(cursor.lastrowid)

    # 대시보드 2: 마케팅 — 커스텀 메트릭
    mkt_metrics = [
        ("광고 지출", "원", "#f87171"),
        ("클릭수", "회", "#60a5fa"),
        ("전환수", "건", "#34d399"),
        ("CPA", "원", "#fbbf24"),
    ]
    mkt_metric_ids = []
    for name, unit, color in mkt_metrics:
        cursor = await db.execute(
            "INSERT INTO custom_metrics (dashboard_id, name, unit, color) VALUES (?,?,?,?)",
            (dash_ids[1], name, unit, color)
        )
        mkt_metric_ids.append(cursor.lastrowid)

    # 대시보드 3: 서비스 — 커스텀 메트릭
    svc_metrics = [
        ("API 호출", "회", "#60a5fa"),
        ("에러율", "%", "#f87171"),
        ("평균 응답시간", "ms", "#fbbf24"),
        ("활성 사용자", "명", "#34d399"),
    ]
    svc_metric_ids = []
    for name, unit, color in svc_metrics:
        cursor = await db.execute(
            "INSERT INTO custom_metrics (dashboard_id, name, unit, color) VALUES (?,?,?,?)",
            (dash_ids[2], name, unit, color)
        )
        svc_metric_ids.append(cursor.lastrowid)

    # 30일치 데이터 시드
    now = datetime.now()
    for day_offset in range(30, 0, -1):
        dt = now - timedelta(days=day_offset)
        ts = dt.strftime("%Y-%m-%d %H:%M:%S")

        # 쇼핑몰
        daily_rev = random.randint(800000, 3500000)
        daily_orders = random.randint(15, 80)
        daily_signups = random.randint(3, 25)
        conv = round(random.uniform(1.8, 5.5), 1)
        cart_abandon = round(random.uniform(55, 78), 1)
        for mid, val in zip(shop_metric_ids, [daily_rev, daily_orders, daily_signups, conv, cart_abandon]):
            await db.execute("INSERT INTO metric_data (metric_id, value, recorded_at) VALUES (?,?,?)", (mid, val, ts))

        # 이벤트
        for _ in range(random.randint(5, 15)):
            etype = random.choices(["order","signup","upgrade","refund"], weights=[50,25,15,10])[0]
            if etype == "order":
                amt = random.choice([29000, 59000, 99000, 199000])
                desc = f"{random.choice(CITIES)}에서 {random.choice(PRODUCTS)} 주문 ({random.choice(NAMES)})"
            elif etype == "signup":
                amt = 0
                desc = f"{random.choice(NAMES)}님 회원가입 ({random.choice(CITIES)})"
            elif etype == "upgrade":
                amt = random.choice([30000, 70000])
                desc = f"{random.choice(NAMES)}님 {random.choice(PRODUCTS[:3])} 업그레이드"
            else:
                amt = -random.choice([29000, 59000])
                desc = f"{random.choice(NAMES)}님 환불 처리"
            evt_ts = (dt + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute("INSERT INTO events (dashboard_id, event_type, description, amount, created_at) VALUES (?,?,?,?,?)",
                             (dash_ids[0], etype, desc, amt, evt_ts))

        # 마케팅
        ad_spend = random.randint(50000, 300000)
        clicks = random.randint(200, 2000)
        conversions = random.randint(5, 80)
        cpa = round(ad_spend / max(conversions, 1))
        for mid, val in zip(mkt_metric_ids, [ad_spend, clicks, conversions, cpa]):
            await db.execute("INSERT INTO metric_data (metric_id, value, recorded_at) VALUES (?,?,?)", (mid, val, ts))

        # 서비스
        api_calls = random.randint(5000, 50000)
        error_rate = round(random.uniform(0.1, 3.5), 2)
        avg_resp = random.randint(45, 350)
        active_users = random.randint(100, 800)
        for mid, val in zip(svc_metric_ids, [api_calls, error_rate, avg_resp, active_users]):
            await db.execute("INSERT INTO metric_data (metric_id, value, recorded_at) VALUES (?,?,?)", (mid, val, ts))

    # 알림
    alert_data = [
        (dash_ids[0], "일 매출 목표 달성", "오늘 매출이 300만원을 돌파했습니다! 🎉", "success"),
        (dash_ids[0], "환불 증가 감지", "최근 1시간 환불 3건 발생", "warning"),
        (dash_ids[1], "캠페인 성과 우수", "네이버 광고 전환율 4.2% 달성", "success"),
        (dash_ids[2], "에러율 상승", "API 에러율이 2%를 초과했습니다", "error"),
        (dash_ids[2], "트래픽 급증", "API 호출량이 평소 대비 200% 증가", "warning"),
    ]
    for did, title, msg, sev in alert_data:
        await db.execute("INSERT INTO alerts (dashboard_id, title, message, severity) VALUES (?,?,?,?)", (did, title, msg, sev))

    # 웹훅
    import uuid
    await db.execute(
        "INSERT INTO webhooks (dashboard_id, name, secret, url_path) VALUES (?,?,?,?)",
        (dash_ids[0], "Shopify 주문", uuid.uuid4().hex[:16], f"wh_{uuid.uuid4().hex[:12]}")
    )

    await db.commit()
    await db.close()
    return user_id

async def run_simulator(dashboard_id: int):
    """특정 대시보드에 실시간 데이터 생성"""
    db = await get_db()
    metrics = await (await db.execute(
        "SELECT id, name FROM custom_metrics WHERE dashboard_id=?", (dashboard_id,)
    )).fetchall()
    await db.close()

    if not metrics:
        return

    while True:
        db = await get_db()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for m in metrics:
            # 메트릭 타입에 따라 적절한 값 생성
            name = m["name"]
            if "매출" in name or "지출" in name:
                val = random.randint(10000, 500000)
            elif "율" in name:
                val = round(random.uniform(0.5, 8.0), 1)
            elif "시간" in name:
                val = random.randint(30, 400)
            else:
                val = random.randint(1, 100)

            await db.execute("INSERT INTO metric_data (metric_id, value, recorded_at) VALUES (?,?,?)", (m["id"], val, ts))

        # 랜덤 이벤트
        etype = random.choices(["order", "signup", "upgrade", "refund"], weights=[50, 25, 15, 10])[0]
        if etype == "order":
            amt = random.choice([29000, 59000, 99000, 199000])
            desc = f"{random.choice(CITIES)}에서 {random.choice(PRODUCTS)} 주문"
        elif etype == "signup":
            amt = 0
            desc = f"{random.choice(NAMES)}님 회원가입"
        elif etype == "upgrade":
            amt = random.choice([30000, 70000])
            desc = f"{random.choice(PRODUCTS[:3])} 업그레이드"
        else:
            amt = -random.choice([29000, 59000])
            desc = "환불 처리"

        await db.execute("INSERT INTO events (dashboard_id, event_type, description, amount) VALUES (?,?,?,?)",
                         (dashboard_id, etype, desc, amt))
        await db.commit()

        # 최신 메트릭 값 조회
        latest = {}
        for m in metrics:
            row = await (await db.execute(
                "SELECT value FROM metric_data WHERE metric_id=? ORDER BY recorded_at DESC LIMIT 1", (m["id"],)
            )).fetchone()
            if row:
                latest[m["name"]] = row["value"]

        await db.close()

        await broadcast(dashboard_id, {
            "type": "update",
            "metrics": latest,
            "event": {
                "type": etype,
                "description": desc,
                "amount": amt,
                "time": datetime.now().strftime("%H:%M:%S"),
            }
        })

        await asyncio.sleep(random.uniform(1.5, 3.5))
