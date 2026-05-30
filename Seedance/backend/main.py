"""
Seedance Studio 后端服务
FastAPI + 异步HTTP中转，支持 EvoLink（图片/音乐/视频草稿）+ 火山引擎（最终成片）
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import httpx
import os
import sentry_sdk
from dotenv import load_dotenv

from routers import image, video_draft, music, final_video, session, payment, auth, sse, models, upload, keys, wizard
from middleware.rate_limit import RateLimitMiddleware
from log_config import get_logger

logger = get_logger(__name__)

load_dotenv()

# ── Sentry ────────────────────────────────────────────────────────────────
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.getenv("DEPLOYMENT_REGION", "production"),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        send_default_pii=False,
    )
    logger.info("Sentry monitoring enabled")
else:
    logger.info("Sentry not configured (set SENTRY_DSN to enable)")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 DB 连接池 + 自动建表
    from store import store
    await store.init_schema()
    # 初始化 HTTP 客户端池
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    logger.info("Seedance Studio 后端启动成功")
    yield
    # 关闭时清理
    await app.state.http_client.aclose()
    from db import close_pool
    await close_pool()
    logger.info("后端服务已关闭")

app = FastAPI(
    title="Seedance Studio API",
    description="Seedance 视频创作工作台后端 - API中转服务",
    version="1.0.0",
    lifespan=lifespan
)

# 频率限制（最外层，先于 CORS）
app.add_middleware(RateLimitMiddleware)

# CORS配置：开发环境宽松，生产环境限制域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # nosemgrep: wildcard-cors — dev mode; credentials disabled per Fetch spec
    allow_credentials=False,  # wildcard + credentials is forbidden by Fetch spec
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(session.router,      prefix="/api/session",      tags=["会话管理"])
app.include_router(image.router,        prefix="/api/image",         tags=["图片生成"])
app.include_router(video_draft.router,  prefix="/api/video-draft",   tags=["视频草稿"])
app.include_router(music.router,        prefix="/api/music",         tags=["音乐生成"])
app.include_router(final_video.router,  prefix="/api/final-video",   tags=["最终成片"])
app.include_router(payment.router,      prefix="/api/payment",       tags=["支付"])
app.include_router(auth.router,         prefix="/api/auth",          tags=["认证"])
app.include_router(sse.router,          prefix="/api/sse",           tags=["实时推送"])
app.include_router(models.router,       prefix="/api/models",        tags=["模型选择"])
app.include_router(upload.router,       prefix="/api/upload",        tags=["文件上传"])
app.include_router(keys.router,         prefix="/api/keys",          tags=["API Keys"])
app.include_router(wizard.router,       prefix="/api",               tags=["ComfyUI"])

@app.get("/")
async def portal():
    """主页（Portal）"""
    path = os.path.join(STATIC_DIR, "portal.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    # fallback: 如果没有 portal.html，返回工作台
    studio_path = os.path.join(STATIC_DIR, "seedance-studio.html")
    if os.path.exists(studio_path):
        return FileResponse(studio_path, media_type="text/html")
    return {
        "service": "Seedance Studio API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/studio")
async def studio():
    """AI 视频创作工作台"""
    path = os.path.join(STATIC_DIR, "seedance-studio.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return {"error": "Studio page not found"}, 404


@app.get("/share/{share_id}")
async def view_share(share_id: str):
    """查看分享的视频"""
    from store import store
    share = await store.get_share(share_id)
    if not share:
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<h1 style='color:#ccc;text-align:center;margin-top:100px'>Share not found or expired</h1>", status_code=404)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Seedance Video</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0a0a; color:#e0e0e0; font-family:system-ui,-apple-system,sans-serif;
       display:flex; flex-direction:column; align-items:center; justify-content:center;
       min-height:100vh; padding:20px; }}
.video-container {{ width:100%; max-width:900px; background:#111; border-radius:12px;
                    overflow:hidden; box-shadow:0 4px 30px rgba(255,255,255,0.05); }}
video {{ width:100%; display:block; }}
.info {{ margin-top:20px; text-align:center; max-width:600px; }}
.info p {{ color:#888; font-size:14px; margin:4px 0; }}
.brand {{ margin-top:30px; }}
.brand a {{ color:#60a5fa; text-decoration:none; font-size:14px; }}
</style>
</head>
<body>
<div class="video-container">
  <video controls autoplay playsinline src="{share['video_url']}"></video>
</div>
<div class="info">
  {f'<p style="color:#999;font-style:italic">{share["prompt_en"]}</p>' if share.get('prompt_en') else ''}
  <p>{share.get('resolution','1080p')} · {share.get('duration',12)}s</p>
</div>
<div class="brand">
  <a href="/">🎬 Made with Seedance Studio</a>
</div>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html)


@app.get("/health")
async def health():
    import asyncio

    from db import get_pool
    from config import settings

    pool, evolink_status, volc_status = await asyncio.gather(
        get_pool(),
        _probe("evolink", "https://api.evolink.ai/v1/models", settings.EVOLINK_API_KEY),
        _probe("volcengine", "https://ark.cn-beijing.volces.com/api/v3/models", settings.VOLC_API_KEY),
    )

    return {
        "status": "ok",
        "db": "connected" if pool else "unavailable",
        "dependencies": {
            "evolink": evolink_status,
            "volcengine": volc_status,
        },
        "service": "seedance-studio-api",
        "version": "1.0.0",
    }


async def _probe(name: str, url: str, key: str | None) -> str:
    if not key:
        return "unconfigured"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {key}"})
        return "ok" if r.status_code < 500 else f"error({r.status_code})"
    except Exception:
        return "unreachable"


@app.post("/admin/init-db")
async def admin_init_db(request: Request):
    """手动触发数据库建表（调试用，需 Admin Key）"""
    auth = request.headers.get("Authorization", "")
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or auth != f"Bearer {admin_key}":
        raise HTTPException(status_code=403, detail="Admin key required")
    results = []
    from store import store
    pool = await store._pg()
    if not pool:
        return {"status": "error", "detail": "No database connection"}

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        return {"status": "error", "detail": f"schema.sql not found at {schema_path}"}

    with open(schema_path) as f:
        sql = f.read()

    for stmt in sql.split(";"):
        lines = stmt.strip().split("\n")
        sql_lines = [l for l in lines if not l.strip().startswith("--") and l.strip()]
        clean = "\n".join(sql_lines).strip()
        if clean:
            try:
                await pool.execute(clean)
                results.append({"ok": True, "sql": clean[:80] + "..."})
            except Exception as e:
                results.append({"ok": False, "sql": clean[:80] + "...", "error": str(e)})

    # Verify tables exist
    tables = await pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    table_names = [r["table_name"] for r in tables]

    return {
        "status": "ok",
        "results": results,
        "tables_found": table_names,
    }
