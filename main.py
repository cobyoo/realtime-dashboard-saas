import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from models import init_db, get_db
from auth import hash_password, verify_password, create_token, get_current_user
from simulator import connected_clients, run_simulator, state

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 데모 시뮬레이터 시작
    task = asyncio.create_task(run_simulator())
    yield
    task.cancel()

app = FastAPI(title="DataPulse", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Auth ───

@app.post("/api/register")
async def register(email: str = Form(...), password: str = Form(...), company: str = Form("")):
    db = await get_db()
    existing = await (await db.execute("SELECT id FROM users WHERE email=?", (email,))).fetchone()
    if existing:
        await db.close()
        raise HTTPException(409, "이미 가입된 이메일입니다")
    pw_hash = hash_password(password)
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash, company) VALUES (?,?,?)",
        (email, pw_hash, company)
    )
    await db.commit()
    uid = cursor.lastrowid
    await db.close()
    token = create_token(uid, email)
    return {"token": token, "email": email}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    db = await get_db()
    row = await (await db.execute("SELECT * FROM users WHERE email=?", (email,))).fetchone()
    await db.close()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다")
    token = create_token(row["id"], email)
    return {"token": token, "email": email}


# ─── Dashboard Data ───

@app.get("/api/kpi")
async def get_kpi(user=Depends(get_current_user)):
    return state

@app.get("/api/events")
async def get_events(limit: int = 20, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
    )).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/alerts")
async def get_alerts(user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM alerts ORDER BY created_at DESC LIMIT 20"
    )).fetchall()
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/chart/{metric_type}")
async def get_chart_data(metric_type: str, limit: int = 30, user=Depends(get_current_user)):
    db = await get_db()
    rows = await (await db.execute(
        "SELECT value, recorded_at FROM metrics WHERE metric_type=? ORDER BY recorded_at DESC LIMIT ?",
        (metric_type, limit)
    )).fetchall()
    await db.close()
    data = [{"value": r["value"], "time": r["recorded_at"]} for r in reversed(rows)]
    return data


# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)


# ─── Pages ───

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
