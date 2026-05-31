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


async def _daily_backup_loop():
    """Background task: run DB backup daily at 3:00 AM local time."""
    import asyncio, datetime, subprocess, gzip, io, uuid
    await asyncio.sleep(10)  # wait for startup to settle

    while True:
        # Sleep until next 3:00 AM
        now = datetime.datetime.now()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)
        wait_sec = (next_run - now).total_seconds()
        logger.info(f"[BACKUP] Next auto-backup at {next_run.strftime('%Y-%m-%d %H:%M')} (in {wait_sec/3600:.1f}h)")
        await asyncio.sleep(wait_sec)

        # Run backup
        db_url = os.getenv("DATABASE_URL", "")
        admin_key = os.getenv("ADMIN_KEY", "")
        if not db_url or not admin_key:
            logger.warning("[BACKUP] Skipped: DATABASE_URL or ADMIN_KEY not set")
            continue

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_id = uuid.uuid4().hex[:8]
            filename = f"seedance_{timestamp}_{backup_id}.sql.gz"

            result = subprocess.run(
                ["pg_dump", db_url, "--no-owner", "--no-acl", "--clean"],
                capture_output=True, text=False, timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"[BACKUP] pg_dump failed: {result.stderr.decode()[:200]}")
                continue

            buf = io.BytesIO()
            with gzip.GzipFile(filename="", fileobj=buf, mode="wb") as gz:
                gz.write(result.stdout)
            compressed = buf.getvalue()

            from services.storage import upload_bytes
            url = await upload_bytes(compressed, "application/gzip", prefix="backups")
            logger.info(f"[BACKUP] ✅ {filename} ({len(compressed)} bytes) → {url}")
        except Exception as e:
            logger.error(f"[BACKUP] Auto-backup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 DB 连接池 + 自动建表
    from store import store
    await store.init_schema()
    # 初始化 HTTP 客户端池
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    # 启动定时备份任务
    import asyncio
    backup_task = asyncio.create_task(_daily_backup_loop())
    logger.info("Seedance Studio 后端启动成功")
    yield
    # 关闭时清理
    backup_task.cancel()
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


@app.get("/privacy")
async def privacy():
    """隐私政策"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Privacy Policy · Seedance Studio</title>
<style>
:root{--bg:#0a0a0f;--text:#e8e8f0;--text2:#9090a8;--accent:#7c6dfa}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.7;padding:40px 24px;max-width:740px;margin:0 auto}
h1{font-size:28px;font-weight:800;margin-bottom:24px;letter-spacing:-.5px}
h1 span{color:var(--accent)}
h2{font-size:18px;font-weight:700;margin:32px 0 12px;color:#fff}
p{margin-bottom:12px;color:var(--text2)}
a{color:var(--accent)}
</style></head>
<body>
<h1><span>Seedance Studio</span> Privacy Policy</h1>
<p>Last updated: May 31, 2026</p>

<h2>1. Information We Collect</h2>
<p>When you create an account, we collect your email address and authentication credentials. When you use our services, we store uploaded images and generated videos to provide the service.</p>

<h2>2. How We Use Your Information</h2>
<p>We use your email for account authentication and service-related communication only. Uploaded content is used solely for AI generation within the scope of your session. We do not use your content to train models.</p>

<h2>3. Data Storage & Security</h2>
<p>Your data is stored on Cloudflare R2 with encryption at rest. Passwords are hashed with bcrypt. API keys are stored as SHA-256 hashes. We do not store plaintext payment information — all payments are processed by Creem.</p>

<h2>4. Third-Party Services</h2>
<p>We use the following third-party services: EvoLink AI (image/video/music generation), Volcano Engine (video rendering), Cloudflare R2 (file storage), Creem (payment processing), and Sentry (error monitoring).</p>

<h2>5. Your Rights</h2>
<p>You can delete your account and all associated data at any time by contacting <a href="mailto:support@see4dance.com">support@see4dance.com</a>. You can also request a copy of your data.</p>

<h2>6. Contact</h2>
<p>For privacy-related inquiries: <a href="mailto:support@see4dance.com">support@see4dance.com</a></p>
</body></html>""")


@app.get("/terms")
async def terms():
    """服务条款"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Terms of Service · Seedance Studio</title>
<style>
:root{--bg:#0a0a0f;--text:#e8e8f0;--text2:#9090a8;--accent:#7c6dfa}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.7;padding:40px 24px;max-width:740px;margin:0 auto}
h1{font-size:28px;font-weight:800;margin-bottom:24px;letter-spacing:-.5px}
h1 span{color:var(--accent)}
h2{font-size:18px;font-weight:700;margin:32px 0 12px;color:#fff}
p,li{margin-bottom:8px;color:var(--text2)}
a{color:var(--accent)}
ul{padding-left:20px}
</style></head>
<body>
<h1><span>Seedance Studio</span> Terms of Service</h1>
<p>Last updated: May 31, 2026</p>

<h2>1. Acceptance of Terms</h2>
<p>By using Seedance Studio ("the Service"), you agree to these Terms. If you do not agree, do not use the Service.</p>

<h2>2. Description of Service</h2>
<p>Seedance Studio is an AI-powered video creation platform. Users upload images and describe their creative ideas; the platform generates preview images, video drafts, music, and final rendered videos using third-party AI models.</p>

<h2>3. Credits & Payments</h2>
<p>All payments are one-time purchases of credits. Credits never expire. Each AI operation (image generation, video drafting, music, final rendering) consumes a specified number of credits based on the model selected. Prices are displayed before each operation.</p>

<h2>4. Refund Policy</h2>
<p>Unused credits are eligible for a full refund within 14 days of purchase. Consumed credits are non-refundable because the associated AI API costs have already been incurred.</p>

<h2>5. Acceptable Use</h2>
<p>You agree not to use the Service to generate: illegal content, hate speech, adult content, deepfakes of real individuals without consent, or content that infringes third-party intellectual property.</p>

<h2>6. Intellectual Property</h2>
<p>You retain ownership of your uploaded content. Videos you generate belong to you. We reserve no rights to your generated content.</p>

<h2>7. Limitation of Liability</h2>
<p>The Service is provided "as is". We are not liable for any damages arising from use of the Service. AI models may occasionally produce unexpected results — we do not guarantee specific outcomes.</p>

<h2>8. Contact</h2>
<p><a href="mailto:support@see4dance.com">support@see4dance.com</a></p>
</body></html>""")
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


@app.post("/admin/backup")
async def admin_backup(request: Request):
    """触发数据库备份 → 上传到 R2（需 Admin Key）"""
    auth = request.headers.get("Authorization", "")
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or auth != f"Bearer {admin_key}":
        raise HTTPException(status_code=403, detail="Admin key required")

    import subprocess
    import uuid

    timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_id = uuid.uuid4().hex[:8]
    filename = f"seedance_backup_{timestamp}_{backup_id}.sql.gz"

    # Run pg_dump from DATABASE_URL
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return {"status": "error", "detail": "DATABASE_URL not configured"}

    result = subprocess.run(
        ["pg_dump", db_url, "--no-owner", "--no-acl", "--clean"],
        capture_output=True, text=False, timeout=300,
    )

    if result.returncode != 0:
        logger.error(f"[BACKUP] pg_dump failed: {result.stderr.decode()[:300]}")
        raise HTTPException(status_code=500, detail=f"pg_dump failed: {result.stderr.decode()[:200]}")

    # gzip
    import gzip, io
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buf, mode="wb") as gz:
        gz.write(result.stdout)
    compressed = buf.getvalue()

    # Upload to R2
    try:
        from services.storage import upload_bytes
        url = await upload_bytes(compressed, "application/gzip", prefix="backups")
    except RuntimeError as e:
        logger.error(f"[BACKUP] Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    logger.info(f"[BACKUP] ✅ {filename} → {url}")
    return {
        "status": "ok",
        "filename": filename,
        "size_bytes": len(compressed),
        "url": url,
        "message": "Backup saved to R2",
    }


@app.get("/admin/backup/list")
async def admin_backup_list(request: Request):
    """列出 R2 中的备份文件（需 Admin Key）"""
    auth = request.headers.get("Authorization", "")
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or auth != f"Bearer {admin_key}":
        raise HTTPException(status_code=403, detail="Admin key required")

    import boto3
    from botocore.config import Config

    r2_key = os.getenv("R2_ACCESS_KEY_ID", "")
    r2_secret = os.getenv("R2_SECRET_ACCESS_KEY", "")
    r2_endpoint = os.getenv("R2_ENDPOINT", "")
    r2_bucket = os.getenv("R2_BUCKET", "seedance-studios")

    if not all([r2_key, r2_secret, r2_endpoint]):
        return {"status": "error", "detail": "R2 not configured"}

    try:
        s3 = boto3.client("s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
            config=Config(signature_version="s3v4", region_name="auto"),
        )
        resp = s3.list_objects_v2(Bucket=r2_bucket, Prefix="backups/")
        files = []
        for obj in resp.get("Contents", []):
            files.append({
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": str(obj["LastModified"]),
            })
        files.sort(key=lambda f: f["last_modified"], reverse=True)
        return {"status": "ok", "files": files[:20], "count": len(files)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
