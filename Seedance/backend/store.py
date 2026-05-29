"""
Session + User 存储 —— PostgreSQL → Redis → 内存 三层降级

优先 PostgreSQL（DATABASE_URL），其次 Redis（REDIS_URL），最后内存。
每笔余额变动在同一 PG 事务中完成：UPDATE balance + INSERT transaction。
"""

import json
import time
import uuid
import os
import hashlib
import logging
from typing import Dict, Optional

logger = logging.getLogger("seedance.store")

from config import settings
from sse_broker import sse_broker

REDIS_URL = os.getenv("REDIS_URL", "")

_redis = None
if REDIS_URL:
    import redis.asyncio as aioredis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)


def _normalize_tx(tx: dict) -> dict:
    """确保 created_at 是 ISO 格式字符串"""
    if isinstance(tx.get("created_at"), (int, float)):
        from datetime import datetime, timezone
        tx["created_at"] = datetime.fromtimestamp(tx["created_at"], tz=timezone.utc).isoformat()
    elif hasattr(tx.get("created_at"), "isoformat"):
        tx["created_at"] = tx["created_at"].isoformat()
    return tx


class SessionStore:
    def __init__(self):
        self._mem: Dict[str, dict] = {}

    # ─── 连接判断 ──────────────────────────────────────────────────────────

    async def _pg(self):
        from db import get_pool
        return await get_pool()

    def _is_redis(self) -> bool:
        return _redis is not None

    # ─── Schema 初始化 ─────────────────────────────────────────────────────

    async def init_schema(self):
        """首次启动时建表（幂等）"""
        pool = await self._pg()
        if not pool:
            print("[INIT_SCHEMA] No PG pool available, skipping schema init")
            return
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        print(f"[INIT_SCHEMA] Looking for schema at: {schema_path}")
        if not os.path.exists(schema_path):
            print(f"[INIT_SCHEMA] schema.sql NOT FOUND at {schema_path}")
            return
        with open(schema_path) as f:
            sql = f.read()
        print(f"[INIT_SCHEMA] Read schema.sql, {len(sql)} bytes")
        # 按语句拆分执行，strip comment-only lines from each segment
        for stmt in sql.split(";"):
            # remove leading/trailing whitespace, then strip comment lines
            lines = stmt.strip().split("\n")
            sql_lines = [l for l in lines if not l.strip().startswith("--") and l.strip()]
            clean = "\n".join(sql_lines).strip()
            if clean:
                try:
                    await pool.execute(clean)
                    print(f"[INIT_SCHEMA] OK: {clean[:60]}...")
                except Exception as e:
                    print(f"[INIT_SCHEMA] FAIL: {e}\n  SQL: {clean[:100]}...")
                    logger.warning(f"Schema statement failed: {e}\n  SQL: {clean[:100]}...")
        print("[INIT_SCHEMA] Schema initialization complete")
        logger.info("DB schema initialized successfully")

    # ─── Session CRUD ──────────────────────────────────────────────────────

    async def create(self) -> str:
        sid = str(uuid.uuid4())
        now = time.time()
        data = {
            "session_id": sid,
            "created_at": now,
            "expires_at": now + settings.SESSION_TTL,
            "assets": {"images": [], "videos": [], "musics": []},
            "tasks": {},
        }
        pool = await self._pg()
        if pool:
            await pool.execute(
                "INSERT INTO sessions (session_id, data, created_at, expires_at) "
                "VALUES ($1, $2, to_timestamp($3), to_timestamp($4))",
                sid, json.dumps(data, ensure_ascii=False), now, now + settings.SESSION_TTL
            )
        elif self._is_redis():
            await _redis.setex(
                f"seedance:session:{sid}", settings.SESSION_TTL,
                json.dumps(data, ensure_ascii=False)
            )
        else:
            self._mem[sid] = data
        return sid

    async def get(self, session_id: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow(
                "SELECT data FROM sessions WHERE session_id=$1 AND expires_at > NOW()",
                session_id
            )
            if row:
                return json.loads(row["data"])
            return None
        elif self._is_redis():
            raw = await _redis.get(f"seedance:session:{session_id}")
            if not raw:
                return None
            s = json.loads(raw)
            if time.time() > s["expires_at"]:
                await _redis.delete(f"seedance:session:{session_id}")
                return None
            return s
        else:
            s = self._mem.get(session_id)
            if not s:
                return None
            if time.time() > s["expires_at"]:
                del self._mem[session_id]
                return None
            return s

    async def require(self, session_id: str) -> dict:
        s = await self.get(session_id)
        if not s:
            raise ValueError(f"Session不存在或已过期：{session_id}")
        return s

    async def _save(self, session_id: str, s: dict):
        ttl = max(1, int(s["expires_at"] - time.time()))
        pool = await self._pg()
        if pool:
            await pool.execute(
                "UPDATE sessions SET data=$1, expires_at=to_timestamp($2) "
                "WHERE session_id=$3",
                json.dumps(s, ensure_ascii=False), s["expires_at"], session_id
            )
        elif self._is_redis():
            await _redis.setex(
                f"seedance:session:{session_id}", ttl,
                json.dumps(s, ensure_ascii=False)
            )

    # ─── 图片操作 ──────────────────────────────────────────────────────────

    async def add_image(self, session_id: str, url: str, thumbnail: str = "") -> str:
        s = await self.require(session_id)
        imgs = s["assets"]["images"]
        if len(imgs) >= 9:
            imgs.pop(0)
        img_id = str(uuid.uuid4())[:8]
        imgs.append({
            "id": img_id, "url": url,
            "thumbnail": thumbnail or url,
            "color_params": {}, "saved_at": time.time()
        })
        await self._save(session_id, s)
        return img_id

    async def save_color_params(self, session_id: str, image_id: str, params: dict) -> bool:
        s = await self.require(session_id)
        for img in s["assets"]["images"]:
            if img["id"] == image_id:
                img["color_params"] = params
                await self._save(session_id, s)
                return True
        return False

    async def get_image_url(self, session_id: str, image_id: str) -> Optional[str]:
        s = await self.require(session_id)
        for img in s["assets"]["images"]:
            if img["id"] == image_id:
                return img["url"]
        return None

    async def delete_image(self, session_id: str, image_id: str) -> bool:
        s = await self.require(session_id)
        imgs = s["assets"]["images"]
        before = len(imgs)
        s["assets"]["images"] = [img for img in imgs if img["id"] != image_id]
        if len(s["assets"]["images"]) == before:
            return False
        await self._save(session_id, s)
        return True

    # ─── 视频操作 ──────────────────────────────────────────────────────────

    async def add_video(self, session_id: str, url: str, thumbnail: str,
                        duration: int, prompt: str) -> str:
        s = await self.require(session_id)
        vids = s["assets"]["videos"]
        if len(vids) >= 3:
            vids.pop(0)
        vid_id = str(uuid.uuid4())[:8]
        vids.append({
            "id": vid_id, "url": url, "thumbnail": thumbnail,
            "duration": duration, "prompt": prompt, "saved_at": time.time()
        })
        await self._save(session_id, s)
        return vid_id

    async def delete_video(self, session_id: str, video_id: str) -> bool:
        s = await self.require(session_id)
        vids = s["assets"]["videos"]
        s["assets"]["videos"] = [v for v in vids if v["id"] != video_id]
        await self._save(session_id, s)
        return True

    # ─── 音乐操作 ──────────────────────────────────────────────────────────

    async def add_music(self, session_id: str, url: str, mood: str,
                        genre: str, duration: int) -> str:
        s = await self.require(session_id)
        musics = s["assets"]["musics"]
        if len(musics) >= 3:
            musics.pop(0)
        mus_id = str(uuid.uuid4())[:8]
        musics.append({
            "id": mus_id, "url": url, "mood": mood,
            "genre": genre, "duration": duration, "saved_at": time.time()
        })
        await self._save(session_id, s)
        return mus_id

    async def delete_music(self, session_id: str, music_id: str) -> bool:
        s = await self.require(session_id)
        musics = s["assets"]["musics"]
        s["assets"]["musics"] = [m for m in musics if m["id"] != music_id]
        await self._save(session_id, s)
        return True

    # ─── 任务跟踪 ──────────────────────────────────────────────────────────

    async def create_task(self, session_id: str, task_type: str, meta: dict = {}) -> str:
        s = await self.require(session_id)
        task_id = str(uuid.uuid4())
        s["tasks"][task_id] = {
            "id": task_id, "type": task_type, "status": "pending",
            "progress": 0, "result_url": None, "error": None,
            "meta": meta, "created_at": time.time()
        }
        await self._save(session_id, s)
        return task_id

    async def update_task(self, session_id: str, task_id: str, **kwargs):
        s = await self.require(session_id)
        task = s["tasks"].get(task_id)
        if task:
            task.update(kwargs)
            await self._save(session_id, s)
            await sse_broker.publish(task_id, {
                "task_id": task_id,
                "status": task.get("status", "processing"),
                "progress": task.get("progress", 0),
                "result_url": task.get("result_url"),
                "error": task.get("error"),
            })

    async def get_task(self, session_id: str, task_id: str) -> Optional[dict]:
        s = await self.require(session_id)
        return s["tasks"].get(task_id)

    # ─── 用户管理 ──────────────────────────────────────────────────────────

    def _make_user_id(self, email: str, phone: str, google_id: str, github_id: str = "") -> str:
        return hashlib.sha256(
            f"{email}{phone}{google_id}{github_id}{time.time()}".encode()
        ).hexdigest()[:16]

    async def create_user(self, email: str = "", phone: str = "",
                          google_id: str = "", github_id: str = "",
                          password_hash: str = "",
                          auth_provider: str = "email") -> str:
        uid = self._make_user_id(email, phone, google_id, github_id)
        currency = "CNY" if settings.DEPLOYMENT_REGION == "cn" else "USD"
        pool = await self._pg()
        if pool:
            try:
                await pool.execute(
                    """INSERT INTO users (user_id, email, phone, google_id, github_id, password_hash,
                       auth_provider, currency)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT (user_id) DO NOTHING""",
                    uid,
                    email or None, phone or None, google_id or None, github_id or None,
                    password_hash, auth_provider, currency
                )
            except Exception as e:
                logger.error(f"create_user PG insert failed: {e}")
                raise
        elif self._is_redis():
            user = {
                "user_id": uid, "email": email, "phone": phone,
                "google_id": google_id, "github_id": github_id,
                "password_hash": password_hash,
                "auth_provider": auth_provider, "avatar_url": "",
                "created_at": time.time(), "balance_subunit": 0,
                "currency": currency,
            }
            await _redis.setex(f"seedance:user:{uid}", 86400 * 365,
                              json.dumps(user, ensure_ascii=False))
            if email:
                await _redis.set(f"seedance:user_email:{email}", uid)
            if phone:
                await _redis.set(f"seedance:user_phone:{phone}", uid)
            if google_id:
                await _redis.set(f"seedance:user_google:{google_id}", uid)
            if github_id:
                await _redis.set(f"seedance:user_github:{github_id}", uid)
        else:
            self._mem[f"user:{uid}"] = {
                "user_id": uid, "email": email, "phone": phone,
                "google_id": google_id, "github_id": github_id,
                "password_hash": password_hash,
                "auth_provider": auth_provider, "avatar_url": "",
                "created_at": time.time(), "balance_subunit": 0,
                "currency": currency,
            }
        return uid

    def _row_to_user(self, row) -> dict:
        """将 PG row 转为 user dict"""
        return {
            "user_id": row["user_id"],
            "email": row["email"] or "",
            "phone": row["phone"] or "",
            "google_id": row["google_id"] or "",
            "github_id": row["github_id"] or "",
            "password_hash": row["password_hash"] or "",
            "auth_provider": row["auth_provider"] or "email",
            "avatar_url": row["avatar_url"] or "",
            "balance_subunit": row["balance_subunit"],
            "currency": row["currency"],
            "created_at": row["created_at"].timestamp() if hasattr(row["created_at"], "timestamp") else time.time(),
        }

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM users WHERE email=$1", email)
            return self._row_to_user(row) if row else None
        elif self._is_redis():
            uid = await _redis.get(f"seedance:user_email:{email}")
            if not uid:
                return None
            raw = await _redis.get(f"seedance:user:{uid}")
            return json.loads(raw) if raw else None
        else:
            for k, v in self._mem.items():
                if k.startswith("user:") and v.get("email") == email:
                    return v
            return None

    async def get_user_by_phone(self, phone: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM users WHERE phone=$1", phone)
            return self._row_to_user(row) if row else None
        elif self._is_redis():
            uid = await _redis.get(f"seedance:user_phone:{phone}")
            if not uid:
                return None
            raw = await _redis.get(f"seedance:user:{uid}")
            return json.loads(raw) if raw else None
        else:
            for k, v in self._mem.items():
                if k.startswith("user:") and v.get("phone") == phone:
                    return v
            return None

    async def get_user_by_google_id(self, google_id: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM users WHERE google_id=$1", google_id)
            return self._row_to_user(row) if row else None
        elif self._is_redis():
            uid = await _redis.get(f"seedance:user_google:{google_id}")
            if not uid:
                return None
            raw = await _redis.get(f"seedance:user:{uid}")
            return json.loads(raw) if raw else None
        else:
            for k, v in self._mem.items():
                if k.startswith("user:") and v.get("google_id") == google_id:
                    return v
            return None

    async def get_user_by_github_id(self, github_id: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM users WHERE github_id=$1", github_id)
            return self._row_to_user(row) if row else None
        elif self._is_redis():
            uid = await _redis.get(f"seedance:user_github:{github_id}")
            if not uid:
                return None
            raw = await _redis.get(f"seedance:user:{uid}")
            return json.loads(raw) if raw else None
        else:
            for k, v in self._mem.items():
                if k.startswith("user:") and v.get("github_id") == github_id:
                    return v
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
            return self._row_to_user(row) if row else None
        elif self._is_redis():
            raw = await _redis.get(f"seedance:user:{user_id}")
            return json.loads(raw) if raw else None
        else:
            return self._mem.get(f"user:{user_id}")

    # ─── 余额操作（PG 事务保证原子性）────────────────────────────────────

    async def topup_balance(self, user_id: str, amount_subunit: int,
                            tx_type: str = "topup", note: str = "") -> int:
        """充值 / 扣款。返回新余额。正数为充值，负数为扣款。"""
        pool = await self._pg()
        if pool:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "UPDATE users SET balance_subunit = balance_subunit + $1 "
                        "WHERE user_id = $2 RETURNING *",
                        amount_subunit, user_id
                    )
                    if not row:
                        raise ValueError("User not found")
                    tx_id = hashlib.sha256(
                        f"{user_id}{tx_type}{time.time()}".encode()
                    ).hexdigest()[:12]
                    await conn.execute(
                        """INSERT INTO transactions
                           (tx_id, user_id, tx_type, amount_subunit, balance_after, currency, note)
                           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                        tx_id, user_id, tx_type, amount_subunit,
                        row["balance_subunit"], row["currency"], note
                    )
                    return row["balance_subunit"]
        elif self._is_redis():
            user = await self.get_user_by_id(user_id)
            if not user:
                raise ValueError("User not found")
            user["balance_subunit"] = user.get("balance_subunit", 0) + amount_subunit
            await _redis.setex(
                f"seedance:user:{user_id}", 86400 * 365,
                json.dumps(user, ensure_ascii=False)
            )
            # 记录交易到 Redis
            tx = {
                "tx_id": hashlib.sha256(f"{user_id}{tx_type}{time.time()}".encode()).hexdigest()[:12],
                "user_id": user_id, "tx_type": tx_type,
                "amount_subunit": amount_subunit,
                "balance_after": user["balance_subunit"],
                "currency": user["currency"], "note": note,
                "created_at": time.time(),
            }
            await _redis.lpush(f"seedance:tx:{user_id}", json.dumps(tx, ensure_ascii=False))
            await _redis.ltrim(f"seedance:tx:{user_id}", 0, 49)
            return user["balance_subunit"]
        else:
            user = self._mem.get(f"user:{user_id}")
            if not user:
                raise ValueError("User not found")
            user["balance_subunit"] = user.get("balance_subunit", 0) + amount_subunit
            # 记录交易到内存
            tx = {
                "tx_id": hashlib.sha256(f"{user_id}{tx_type}{time.time()}".encode()).hexdigest()[:12],
                "user_id": user_id, "tx_type": tx_type,
                "amount_subunit": amount_subunit,
                "balance_after": user["balance_subunit"],
                "currency": user["currency"], "note": note,
                "created_at": time.time(),
            }
            self._mem.setdefault(f"tx:{user_id}", []).insert(0, tx)
            if len(self._mem[f"tx:{user_id}"]) > 50:
                self._mem[f"tx:{user_id}"] = self._mem[f"tx:{user_id}"][:50]
            return user["balance_subunit"]

    # ─── 交易记录 ──────────────────────────────────────────────────────────

    async def get_transactions(self, user_id: str, limit: int = 50) -> list:
        pool = await self._pg()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM transactions WHERE user_id=$1 "
                "ORDER BY created_at DESC LIMIT $2",
                user_id, limit
            )
            return [
                {
                    "tx_id": r["tx_id"],
                    "user_id": r["user_id"],
                    "tx_type": r["tx_type"],
                    "amount_subunit": r["amount_subunit"],
                    "balance_after": r["balance_after"],
                    "currency": r["currency"],
                    "note": r["note"],
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ]
        elif self._is_redis():
            raw_list = await _redis.lrange(f"seedance:tx:{user_id}", 0, limit - 1)
            return [_normalize_tx(json.loads(r)) for r in raw_list if r]
        else:
            return [_normalize_tx(tx) for tx in self._mem.get(f"tx:{user_id}", [])]

    # ─── 分享链接 ──────────────────────────────────────────────────────────

    async def create_share(self, video_url: str, prompt_en: str = "",
                           resolution: str = "1080p", duration: int = 12,
                           thumbnail_url: str = "", user_id: str = "") -> str:
        """创建视频分享链接，返回 share_id"""
        share_id = str(uuid.uuid4())[:8]
        pool = await self._pg()
        if pool:
            await pool.execute(
                """INSERT INTO shares (share_id, video_url, prompt_en, resolution, duration, thumbnail_url, user_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                share_id, video_url, prompt_en, resolution, duration, thumbnail_url, user_id or None
            )
        elif self._is_redis():
            share = {
                "share_id": share_id, "video_url": video_url, "prompt_en": prompt_en,
                "resolution": resolution, "duration": duration, "thumbnail_url": thumbnail_url,
                "user_id": user_id, "created_at": time.time(),
            }
            await _redis.setex(f"seedance:share:{share_id}", 86400 * 30,
                              json.dumps(share, ensure_ascii=False))
        else:
            self._mem[f"share:{share_id}"] = {
                "share_id": share_id, "video_url": video_url, "prompt_en": prompt_en,
                "resolution": resolution, "duration": duration, "thumbnail_url": thumbnail_url,
                "user_id": user_id, "created_at": time.time(),
            }
        return share_id

    async def get_share(self, share_id: str) -> Optional[dict]:
        """获取分享记录"""
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow("SELECT * FROM shares WHERE share_id=$1", share_id)
            if row:
                return {
                    "share_id": row["share_id"], "video_url": row["video_url"],
                    "prompt_en": row["prompt_en"] or "",
                    "resolution": row["resolution"] or "1080p",
                    "duration": row["duration"] or 12,
                    "thumbnail_url": row.get("thumbnail_url") or "",
                    "user_id": row.get("user_id") or "",
                    "created_at": row["created_at"].isoformat(),
                }
            return None
        elif self._is_redis():
            raw = await _redis.get(f"seedance:share:{share_id}")
            return json.loads(raw) if raw else None
        else:
            return self._mem.get(f"share:{share_id}")

    # ─── 视频任务映射（ComfyUI）─────────────────────────────────────────────

    async def save_video_task(self, task_id: str, user_id: str, evo_task_id: str,
                              provider: str = "evolink"):
        """保存 ComfyUI 视频任务 → remote task_id 映射"""
        pool = await self._pg()
        if pool:
            await pool.execute(
                """INSERT INTO sessions (session_id, data, created_at, expires_at)
                   VALUES ($1, $2, NOW(), NOW() + INTERVAL '24 hours')
                   ON CONFLICT (session_id) DO UPDATE
                   SET data=$2, expires_at=NOW() + INTERVAL '24 hours'""",
                f"vtask:{task_id}",
                json.dumps({"evo_task_id": evo_task_id, "user_id": user_id,
                            "provider": provider})
            )
        elif self._is_redis():
            await _redis.setex(f"vtask:{task_id}", 86400,
                              json.dumps({"evo_task_id": evo_task_id, "user_id": user_id,
                                          "provider": provider}))

    async def get_video_task(self, task_id: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow(
                "SELECT data FROM sessions WHERE session_id=$1 AND expires_at > NOW()",
                f"vtask:{task_id}"
            )
            return json.loads(row["data"]) if row else None
        elif self._is_redis():
            raw = await _redis.get(f"vtask:{task_id}")
            return json.loads(raw) if raw else None
        return None

    # ─── API Key 管理 ───────────────────────────────────────────────────────

    async def create_api_key(self, user_id: str, key_id: str,
                             key_hash: str, key_prefix: str,
                             name: str = "") -> str:
        pool = await self._pg()
        if pool:
            await pool.execute(
                """INSERT INTO api_keys (key_id, user_id, key_hash, key_prefix, name)
                   VALUES ($1, $2, $3, $4, $5)""",
                key_id, user_id, key_hash, key_prefix, name
            )
        return key_id

    async def get_api_keys(self, user_id: str) -> list:
        pool = await self._pg()
        if pool:
            rows = await pool.fetch(
                """SELECT key_id, key_prefix, name, last_used_at, created_at
                   FROM api_keys WHERE user_id=$1 AND revoked_at IS NULL
                   ORDER BY created_at DESC""",
                user_id
            )
            return [
                {
                    "key_id": r["key_id"],
                    "key_prefix": r["key_prefix"],
                    "name": r["name"] or "",
                    "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ]
        return []

    async def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]:
        pool = await self._pg()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM api_keys WHERE key_hash=$1 AND revoked_at IS NULL",
                key_hash
            )
            return dict(row) if row else None
        return None

    async def touch_api_key(self, key_id: str):
        pool = await self._pg()
        if pool:
            await pool.execute(
                "UPDATE api_keys SET last_used_at=NOW() WHERE key_id=$1",
                key_id
            )

    async def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        pool = await self._pg()
        if pool:
            result = await pool.execute(
                "UPDATE api_keys SET revoked_at=NOW() WHERE key_id=$1 AND user_id=$2 AND revoked_at IS NULL",
                key_id, user_id
            )
            return "UPDATE 1" in (result or "")
        return False

    # ─── 清理 ──────────────────────────────────────────────────────────────

    async def cleanup_expired(self):
        if self._pg() or self._is_redis():
            return 0  # PG/Redis 自动过期
        now = time.time()
        expired = [sid for sid, s in self._mem.items()
                   if isinstance(s, dict) and now > s.get("expires_at", now + 1)]
        for sid in expired:
            del self._mem[sid]
        return len(expired)


store = SessionStore()
