from datetime import datetime, timedelta, timezone
import hashlib
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models import get_db

SECRET_KEY = "datapulse-secret-key-change-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)

def hash_password(pw: str) -> str:
    return hashlib.sha256((pw + SECRET_KEY).encode()).hexdigest()

def verify_password(pw: str, hashed: str) -> bool:
    return hash_password(pw) == hashed

def create_token(user_id: int, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)):
    if not cred:
        raise HTTPException(401, "인증이 필요합니다")
    try:
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {"id": int(payload["sub"]), "email": payload["email"]}
    except JWTError:
        raise HTTPException(401, "토큰이 만료되었습니다")

async def get_user_by_api_key(x_api_key: str = Header(None)):
    """API 키로 사용자 인증 (외부 연동용)"""
    if not x_api_key:
        raise HTTPException(401, "X-API-Key 헤더가 필요합니다")
    db = await get_db()
    row = await (await db.execute(
        "SELECT ak.user_id, ak.id as key_id FROM api_keys ak WHERE ak.key=? AND ak.active=1",
        (x_api_key,)
    )).fetchone()
    await db.close()
    if not row:
        raise HTTPException(401, "유효하지 않은 API 키입니다")
    return {"user_id": row["user_id"], "key_id": row["key_id"]}
