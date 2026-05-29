"""
认证路由
POST /api/auth/register   → 注册（手机/邮箱）
POST /api/auth/login      → 登录
POST /api/auth/google     → Google OAuth
GET  /api/auth/github     → GitHub OAuth 授权入口
GET  /api/auth/github/callback → GitHub OAuth 回调
GET  /api/auth/me         → 获取当前用户信息
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, Literal
import jwt
import bcrypt
import os
import time
import urllib.parse
import hashlib
import secrets

from config import settings
from store import store

router = APIRouter()

JWT_SECRET = settings.JWT_SECRET
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is required. Set it in backend/.env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = 86400 * 7  # 7 days


def create_jwt(user_id: str) -> str:
    return jwt.encode({
        "user_id": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY,
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> Optional[str]:
    """返回 user_id 或 None"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ─── 请求模型 ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str
    auth_provider: Literal["email", "phone"] = "email"


class LoginRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


# ─── 路由 ─────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    """注册新用户"""
    try:
        if req.auth_provider == "email":
            if not req.email:
                raise HTTPException(status_code=400, detail="Email is required")
            existing = await store.get_user_by_email(req.email)
            if existing:
                raise HTTPException(status_code=409, detail="Email already registered")
            user_id = await store.create_user(
                email=req.email,
                password_hash=hash_password(req.password),
                auth_provider="email"
            )
        else:
            if not req.phone:
                raise HTTPException(status_code=400, detail="Phone is required")
            existing = await store.get_user_by_phone(req.phone)
            if existing:
                raise HTTPException(status_code=409, detail="Phone already registered")
            user_id = await store.create_user(
                phone=req.phone,
                password_hash=hash_password(req.password),
                auth_provider="phone"
            )

        token = create_jwt(user_id)
        return {
            "success": True,
            "user_id": user_id,
            "token": token,
            "expires_in": JWT_EXPIRY,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[REGISTER ERROR] {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Registration failed due to an internal error")


@router.post("/login")
async def login(req: LoginRequest):
    """登录"""
    user = None
    if req.email:
        user = await store.get_user_by_email(req.email)
    elif req.phone:
        user = await store.get_user_by_phone(req.phone)
    else:
        raise HTTPException(status_code=400, detail="Email or phone required")

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Use Google OAuth to login")

    if not check_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_jwt(user["user_id"])
    return {
        "success": True,
        "user_id": user["user_id"],
        "token": token,
        "expires_in": JWT_EXPIRY,
    }


@router.post("/google")
async def google_auth(req: GoogleAuthRequest, request: Request):
    """Google OAuth 登录 —— 验证 id_token，自动创建/登录用户"""
    import httpx

    # 验证 Google ID Token
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={req.id_token}",
                timeout=15.0
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid Google ID token")
            token_info = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        print(f"[GOOGLE AUTH] Token verification error: {e}")
        raise HTTPException(status_code=502, detail="Google token verification failed")

    # 验证 audience（如果有配置 GOOGLE_CLIENT_ID）
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if client_id and token_info.get("aud") != client_id:
        raise HTTPException(status_code=401, detail="Token audience mismatch")

    google_id = token_info.get("sub")
    email = token_info.get("email", "")
    name = token_info.get("name", "")
    avatar = token_info.get("picture", "")

    if not google_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    # 查找或创建用户
    user = await store.get_user_by_google_id(google_id)
    if not user and email:
        # 尝试通过 email 查找并关联
        user = await store.get_user_by_email(email)

    if not user:
        # 新用户：通过 Google 注册
        user_id = await store.create_user(
            email=email,
            google_id=google_id,
            password_hash="",
            auth_provider="google"
        )
        # 更新头像
        if avatar:
            pool = await store._pg()
            if pool:
                await pool.execute(
                    "UPDATE users SET avatar_url=$1 WHERE user_id=$2",
                    avatar, user_id
                )
        user = await store.get_user_by_id(user_id)
    elif not user.get("google_id"):
        # 已有 email 注册用户，关联 Google ID
        pool = await store._pg()
        if pool:
            await pool.execute(
                "UPDATE users SET google_id=$1, avatar_url=COALESCE(NULLIF($2,''), avatar_url) WHERE user_id=$3",
                google_id, avatar, user["user_id"]
            )
        user = await store.get_user_by_id(user["user_id"])

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create/find user")

    token = create_jwt(user["user_id"])
    return {
        "success": True,
        "user_id": user["user_id"],
        "token": token,
        "expires_in": JWT_EXPIRY,
        "is_new": user.get("auth_provider") == "google" and not user.get("password_hash"),
    }


@router.get("/config")
async def auth_config():
    """返回前端需要的认证配置（Google Client ID 等）"""
    return {
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "github_client_id": os.getenv("GITHUB_CLIENT_ID", ""),
    }


@router.get("/github")
async def github_auth():
    """GitHub OAuth 入口 —— 返回授权 URL，前端直接跳转"""
    client_id = os.getenv("GITHUB_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")
    callback_url = os.getenv("BASE_URL", "https://see4dance.com") + "/api/auth/github/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": "user:email",
    }
    url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
    return {"url": url}


@router.get("/github/callback")
async def github_callback(code: str = ""):
    """GitHub OAuth 回调 —— 用 code 换 token，获取用户信息，返回 JWT"""
    import httpx

    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    client_id = os.getenv("GITHUB_CLIENT_ID", "")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    base_url = os.getenv("BASE_URL", "https://see4dance.com")
    callback_url = base_url + "/api/auth/github/callback"

    # 1. Exchange code for access_token
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": callback_url,
                },
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"GitHub token exchange failed: {resp.status_code}")
            token_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        print(f"[GITHUB AUTH] Token exchange error: {e}")
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="GitHub authorization denied")

    # 2. Get user info
    try:
        async with httpx.AsyncClient() as http:
            user_resp = await http.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=15.0,
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch GitHub user info")
            gh_user = user_resp.json()
    except HTTPException:
        raise
    except Exception as e:
        print(f"[GITHUB AUTH] User fetch error: {e}")
        raise HTTPException(status_code=502, detail="GitHub user fetch failed")

    github_id = str(gh_user.get("id", ""))
    login = gh_user.get("login", "")
    name = gh_user.get("name") or login
    avatar = gh_user.get("avatar_url", "")

    # 3. Try to get email (may need separate call)
    email = gh_user.get("email") or ""
    if not email:
        try:
            async with httpx.AsyncClient() as http:
                emails_resp = await http.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=15.0,
                )
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    primary = [e for e in emails if e.get("primary")]
                    if primary:
                        email = primary[0]["email"]
                    elif emails:
                        email = emails[0]["email"]
        except Exception:
            print(f"[auth] GitHub email fetch failed (non-fatal)")
            pass  # email is optional

    if not github_id:
        raise HTTPException(status_code=401, detail="Invalid GitHub user: missing id")

    # 4. Find or create user
    user = await store.get_user_by_github_id(github_id)
    if not user and email:
        user = await store.get_user_by_email(email)

    is_new = False
    if not user:
        user_id = await store.create_user(
            email=email,
            github_id=github_id,
            password_hash="",
            auth_provider="github"
        )
        is_new = True
        if avatar:
            pool = await store._pg()
            if pool:
                await pool.execute(
                    "UPDATE users SET avatar_url=$1 WHERE user_id=$2",
                    avatar, user_id
                )
        user = await store.get_user_by_id(user_id)
    elif not user.get("github_id"):
        pool = await store._pg()
        if pool:
            await pool.execute(
                "UPDATE users SET github_id=$1, avatar_url=COALESCE(NULLIF($2,''), avatar_url) WHERE user_id=$3",
                github_id, avatar, user["user_id"]
            )
        user = await store.get_user_by_id(user["user_id"])

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create/find user")

    token = create_jwt(user["user_id"])

    # 5. Redirect to frontend with token
    frontend_url = base_url + "?token=" + token
    if is_new:
        frontend_url += "&new=1"
    return RedirectResponse(url=frontend_url)


class ComfyuiActivateRequest(BaseModel):
    email: str
    password: str


@router.post("/comfyui/register")
async def comfyui_register(req: ComfyuiActivateRequest):
    """ComfyUI 设备注册 + 激活 —— 邮箱注册并自动返回 API Key"""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = await store.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered. Please login instead.")

    # Create user
    user_id = await store.create_user(
        email=req.email,
        password_hash=hash_password(req.password),
        auth_provider="email"
    )
    token = create_jwt(user_id)

    # Auto-create API key
    key_id = secrets.token_hex(6)
    random_part = secrets.token_hex(10)
    plaintext = f"sk-seed-{key_id}{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    key_prefix = plaintext[:14] + "***"
    await store.create_api_key(user_id, key_id, key_hash, key_prefix, "ComfyUI")

    return {
        "success": True,
        "token": token,
        "user_id": user_id,
        "email": req.email,
        "api_key": plaintext,
        "api_key_prefix": key_prefix,
        "is_new": True,
    }


@router.post("/comfyui/activate")
async def comfyui_activate(req: ComfyuiActivateRequest):
    """ComfyUI 设备激活 —— 邮箱+密码登录，自动创建/返回 API Key"""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = await store.get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found. Please register at see4dance.com first.")

    if not user.get("password_hash"):
        raise HTTPException(status_code=401,
                           detail="This account uses OAuth login. Please set a password in web portal first.")

    if not check_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid password")

    user_id = user["user_id"]
    token = create_jwt(user_id)

    # Auto-create API key (or reuse existing active one)
    existing_keys = await store.get_api_keys(user_id)
    if existing_keys:
        # Return existing key info (but not the plaintext - user needs to create new if lost)
        return {
            "success": True,
            "token": token,
            "user_id": user_id,
            "email": user.get("email", ""),
            "api_key_hint": "You have existing API keys. Check web portal or create a new one.",
            "has_api_key": True,
        }

    # Create new API key
    key_id = secrets.token_hex(6)
    random_part = secrets.token_hex(10)
    plaintext = f"sk-seed-{key_id}{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    key_prefix = plaintext[:14] + "***"

    await store.create_api_key(user_id, key_id, key_hash, key_prefix, "ComfyUI")

    return {
        "success": True,
        "token": token,
        "user_id": user_id,
        "email": user.get("email", ""),
        "api_key": plaintext,
        "api_key_prefix": key_prefix,
        "has_api_key": True,
        "hint": "API key auto-created. Store it securely.",
    }


@router.get("/me")
async def get_current_user(request: Request):
    """获取当前用户信息（需 Authorization: Bearer <token>）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    user_id = verify_jwt(auth_header[7:])
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": {
            "user_id": user["user_id"],
            "email": user.get("email"),
            "phone": user.get("phone"),
            "auth_provider": user["auth_provider"],
            "avatar_url": user.get("avatar_url"),
            "balance_subunit": user["balance_subunit"],
            "currency": user["currency"],
        }
    }
