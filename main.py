import asyncio
import csv
import io
import uuid
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Form, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from models import init_db, get_db, gen_api_key
from auth import hash_password, verify_password, create_token, get_current_user, get_user_by_api_key
from simulator import connected_clients, seed_demo_data, run_simulator

active_simulators: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    user_id = await seed_demo_data()
    # 데모 대시보드들에 시뮬레이터 시작
    if user_id:
        db = await get_db()
        rows = await (await db.execute("SELECT id FROM dashboards WHERE user_id=?", (user_id,))).fetchall()
        await db.close()
        for r in rows:
            task = asyncio.create_task(run_simulator(r["id"]))
            active_simulators[r["id"]] = task
    yield
    for t in active_simulators.values():
        t.cancel()

app = FastAPI(title="DataPulse", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ═══════ Auth ═══════

@app.post("/api/register")
async def register(email: str = Form(...), password: str = Form(...), company: str = Form("")):
    db = await get_db()
    if await (await db.execute("SELECT id FROM users WHERE email=?", (email,))).fetchone():
        await db.close()
        raise HTTPException(409, "이미 가입된 이메일입니다")
    pw_hash = hash_password(password)
    cursor = await db.execute("INSERT INTO users (email, password_hash, company) VALUES (?,?,?)", (email, pw_hash, company))
    uid = cursor.lastrowid
    # 기본 API 키 + 대시보드 생성
    await db.execute("INSERT INTO api_keys (user_id, key, name) VALUES (?,?,?)", (uid, gen_api_key(), "Default"))
    await db.execute("INSERT INTO dashboards (user_id, name, description, embed_token) VALUES (?,?,?,?)",
                     (uid, "내 대시보드", "기본 대시보드", uuid.uuid4().hex[:16]))
    await db.commit()
    await db.close()
    return {"token": create_token(uid, email), "email": email}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    db = await get_db()
    row = await (await db.execute("SELECT * FROM users WHERE email=?", (email,))).fetchone()
    await db.close()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다")
    return {"token": create_token(row["id"], email), "email": email}


# ═══════ Dashboards ═══════

@app.get("/api/dashboards")
async def list_dashboards(user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT d.*, (SELECT COUNT(*) FROM custom_metrics WHERE dashboard_id=d.id) as metric_count FROM dashboards d WHERE d.user_id=? ORDER BY d.created_at",
        (user["id"],)
    )).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/dashboards")
async def create_dashboard(name: str = Form(...), description: str = Form(""), user=Depends(get_current_user)):
    db = await get_db()
    cursor = await db.execute("INSERT INTO dashboards (user_id, name, description, embed_token) VALUES (?,?,?,?)",
                              (user["id"], name, description, uuid.uuid4().hex[:16]))
    await db.commit()
    dash = dict(await (await db.execute("SELECT * FROM dashboards WHERE id=?", (cursor.lastrowid,))).fetchone())
    await db.close()
    return dash

@app.delete("/api/dashboards/{dash_id}")
async def delete_dashboard(dash_id: int, user=Depends(get_current_user)):
    db = await get_db()
    await db.execute("DELETE FROM dashboards WHERE id=? AND user_id=?", (dash_id, user["id"]))
    await db.commit()
    await db.close()
    if dash_id in active_simulators:
        active_simulators[dash_id].cancel()
        del active_simulators[dash_id]
    return {"ok": True}


# ═══════ Custom Metrics ═══════

@app.get("/api/dashboards/{dash_id}/metrics")
async def list_metrics(dash_id: int, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute("SELECT * FROM custom_metrics WHERE dashboard_id=?", (dash_id,))).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/dashboards/{dash_id}/metrics")
async def create_metric(dash_id: int, name: str = Form(...), unit: str = Form(""), color: str = Form("#34d399"), user=Depends(get_current_user)):
    db = await get_db()
    cursor = await db.execute("INSERT INTO custom_metrics (dashboard_id, name, unit, color) VALUES (?,?,?,?)", (dash_id, name, unit, color))
    await db.commit()
    metric = dict(await (await db.execute("SELECT * FROM custom_metrics WHERE id=?", (cursor.lastrowid,))).fetchone())
    await db.close()
    return metric

@app.delete("/api/metrics/{metric_id}")
async def delete_metric(metric_id: int, user=Depends(get_current_user)):
    db = await get_db()
    await db.execute("DELETE FROM custom_metrics WHERE id=?", (metric_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


# ═══════ Metric Data ═══════

@app.get("/api/dashboards/{dash_id}/data")
async def get_dashboard_data(dash_id: int, days: int = 30, user=Depends(get_current_user)):
    db = await get_db()
    metrics = await (await db.execute("SELECT * FROM custom_metrics WHERE dashboard_id=?", (dash_id,))).fetchall()
    result = {}
    for m in metrics:
        rows = await (await db.execute(
            "SELECT value, recorded_at FROM metric_data WHERE metric_id=? ORDER BY recorded_at DESC LIMIT ?",
            (m["id"], days * 24)
        )).fetchall()
        result[m["name"]] = {
            "id": m["id"], "unit": m["unit"], "color": m["color"],
            "data": [{"value": r["value"], "time": r["recorded_at"]} for r in reversed(rows)]
        }
    await db.close()
    return result

@app.get("/api/dashboards/{dash_id}/latest")
async def get_latest(dash_id: int, user=Depends(get_current_user)):
    db = await get_db()
    metrics = await (await db.execute("SELECT * FROM custom_metrics WHERE dashboard_id=?", (dash_id,))).fetchall()
    result = {}
    for m in metrics:
        row = await (await db.execute(
            "SELECT value FROM metric_data WHERE metric_id=? ORDER BY recorded_at DESC LIMIT 1", (m["id"],)
        )).fetchone()
        prev = await (await db.execute(
            "SELECT value FROM metric_data WHERE metric_id=? ORDER BY recorded_at DESC LIMIT 1 OFFSET 1", (m["id"],)
        )).fetchone()
        result[m["name"]] = {
            "value": row["value"] if row else 0,
            "prev": prev["value"] if prev else 0,
            "unit": m["unit"], "color": m["color"], "id": m["id"]
        }
    await db.close()
    return result

@app.get("/api/dashboards/{dash_id}/events")
async def get_events(dash_id: int, limit: int = 30, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM events WHERE dashboard_id=? ORDER BY created_at DESC LIMIT ?", (dash_id, limit)
    )).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/dashboards/{dash_id}/alerts")
async def get_alerts(dash_id: int, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM alerts WHERE dashboard_id=? ORDER BY created_at DESC LIMIT 20", (dash_id,)
    )).fetchall()
    await db.close()
    return [dict(r) for r in rows]


# ═══════ External API (API Key Auth) ═══════

@app.post("/api/v1/push")
async def push_data(
    dashboard_id: int = Form(...),
    metric_name: str = Form(...),
    value: float = Form(...),
    auth=Depends(get_user_by_api_key),
):
    db = await get_db()
    metric = await (await db.execute(
        "SELECT cm.id FROM custom_metrics cm JOIN dashboards d ON cm.dashboard_id=d.id WHERE d.user_id=? AND d.id=? AND cm.name=?",
        (auth["user_id"], dashboard_id, metric_name)
    )).fetchone()
    if not metric:
        await db.close()
        raise HTTPException(404, "메트릭을 찾을 수 없습니다")
    await db.execute("INSERT INTO metric_data (metric_id, value) VALUES (?,?)", (metric["id"], value))
    await db.commit()
    await db.close()
    from simulator import broadcast
    await broadcast(dashboard_id, {"type": "metric", "name": metric_name, "value": value})
    return {"ok": True}

@app.post("/api/v1/event")
async def push_event(
    dashboard_id: int = Form(...),
    event_type: str = Form(...),
    description: str = Form(...),
    amount: float = Form(0),
    auth=Depends(get_user_by_api_key),
):
    db = await get_db()
    await db.execute("INSERT INTO events (dashboard_id, event_type, description, amount) VALUES (?,?,?,?)",
                     (dashboard_id, event_type, description, amount))
    await db.commit()
    await db.close()
    return {"ok": True}


# ═══════ CSV Upload ═══════

@app.post("/api/dashboards/{dash_id}/csv")
async def upload_csv(dash_id: int, file: UploadFile = File(...), user=Depends(get_current_user)):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    db = await get_db()
    count = 0
    for row in reader:
        for col, val in row.items():
            if col.lower() in ("date", "날짜", "time", "시간", "recorded_at"):
                continue
            try:
                fval = float(val.replace(",", ""))
            except (ValueError, AttributeError):
                continue
            # 메트릭 없으면 자동 생성
            metric = await (await db.execute(
                "SELECT id FROM custom_metrics WHERE dashboard_id=? AND name=?", (dash_id, col)
            )).fetchone()
            if not metric:
                cursor = await db.execute(
                    "INSERT INTO custom_metrics (dashboard_id, name) VALUES (?,?)", (dash_id, col)
                )
                mid = cursor.lastrowid
            else:
                mid = metric["id"]

            ts = row.get("date") or row.get("날짜") or row.get("time") or row.get("recorded_at") or None
            if ts:
                await db.execute("INSERT INTO metric_data (metric_id, value, recorded_at) VALUES (?,?,?)", (mid, fval, ts))
            else:
                await db.execute("INSERT INTO metric_data (metric_id, value) VALUES (?,?)", (mid, fval))
            count += 1

    await db.commit()
    await db.close()
    return {"imported": count}


# ═══════ API Keys ═══════

@app.get("/api/keys")
async def list_keys(user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute("SELECT id, key, name, active, created_at FROM api_keys WHERE user_id=?", (user["id"],))).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/keys")
async def create_key(name: str = Form("New Key"), user=Depends(get_current_user)):
    db = await get_db()
    key = gen_api_key()
    await db.execute("INSERT INTO api_keys (user_id, key, name) VALUES (?,?,?)", (user["id"], key, name))
    await db.commit()
    await db.close()
    return {"key": key, "name": name}

@app.delete("/api/keys/{key_id}")
async def delete_key(key_id: int, user=Depends(get_current_user)):
    db = await get_db()
    await db.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, user["id"]))
    await db.commit()
    await db.close()
    return {"ok": True}


# ═══════ Embed ═══════

@app.get("/api/embed/{token}")
async def embed_data(token: str):
    db = await get_db()
    dash = await (await db.execute("SELECT * FROM dashboards WHERE embed_token=?", (token,))).fetchone()
    if not dash:
        await db.close()
        raise HTTPException(404)
    metrics = await (await db.execute("SELECT * FROM custom_metrics WHERE dashboard_id=?", (dash["id"],))).fetchall()
    result = {"dashboard": dict(dash), "metrics": {}}
    for m in metrics:
        rows = await (await db.execute(
            "SELECT value, recorded_at FROM metric_data WHERE metric_id=? ORDER BY recorded_at DESC LIMIT 30",
            (m["id"],)
        )).fetchall()
        result["metrics"][m["name"]] = {
            "unit": m["unit"], "color": m["color"],
            "data": [{"value": r["value"], "time": r["recorded_at"]} for r in reversed(rows)]
        }
    await db.close()
    return result


# ═══════ Webhooks ═══════

@app.get("/api/dashboards/{dash_id}/webhooks")
async def list_webhooks(dash_id: int, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute("SELECT * FROM webhooks WHERE dashboard_id=?", (dash_id,))).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/dashboards/{dash_id}/webhooks")
async def create_webhook(dash_id: int, name: str = Form(...), user=Depends(get_current_user)):
    db = await get_db()
    secret = uuid.uuid4().hex[:16]
    url_path = f"wh_{uuid.uuid4().hex[:12]}"
    await db.execute("INSERT INTO webhooks (dashboard_id, name, secret, url_path) VALUES (?,?,?,?)",
                     (dash_id, name, secret, url_path))
    await db.commit()
    await db.close()
    return {"url_path": url_path, "secret": secret}

@app.post("/webhook/{url_path}")
async def receive_webhook(url_path: str):
    """외부에서 웹훅으로 이벤트 수신"""
    db = await get_db()
    wh = await (await db.execute("SELECT * FROM webhooks WHERE url_path=? AND active=1", (url_path,))).fetchone()
    if not wh:
        await db.close()
        raise HTTPException(404)
    # 이벤트 저장
    await db.execute("INSERT INTO events (dashboard_id, event_type, description) VALUES (?,?,?)",
                     (wh["dashboard_id"], "webhook", f"웹훅 수신: {wh['name']}"))
    await db.commit()
    await db.close()
    return {"ok": True}


# ═══════ WebSocket ═══════

@app.websocket("/ws/{dash_id}")
async def websocket_endpoint(ws: WebSocket, dash_id: int):
    await ws.accept()
    if dash_id not in connected_clients:
        connected_clients[dash_id] = set()
    connected_clients[dash_id].add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.get(dash_id, set()).discard(ws)


# ═══════ Pages ═══════

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
