"""
PostgreSQL 连接池管理
- DATABASE_URL 存在 → 创建 asyncpg pool
- 不可用时返回 None，调用方降级到 Redis / 内存
"""

import os
import asyncpg
import socket
from log_config import get_logger

logger = get_logger(__name__)

_pool = None


def _test_tcp(host, port):
    """测试 TCP 连通性"""
    try:
        s = socket.create_connection((host, port), timeout=5.0)
        s.close()
        return True
    except Exception as e:
        logger.error(f"[DB] TCP test to {host}:{port} FAILED: {e}")
        return False


async def get_pool():
    """返回连接池，数据库不可用时返回 None"""
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL", "")
        if database_url:
            from urllib.parse import urlparse
            u = urlparse(database_url)
            host = u.hostname
            port = u.port or 5432
            user = u.username
            password = u.password
            database = u.path.lstrip("/")

            logger.info(f"[DB] target: {host}:{port} user={user} db={database}")

            # 先测 TCP
            if not _test_tcp(host, port):
                logger.info("[DB] TCP unreachable, aborting")
                return None

            logger.info("[DB] TCP OK, trying asyncpg...")

            try:
                _pool = await asyncpg.create_pool(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    min_size=1,
                    max_size=5,
                    timeout=15.0,
                    ssl=False,
                )
                logger.info("[DB] Pool created successfully")
            except Exception as e:
                import traceback
                logger.error(f"[DB] asyncpg pool create failed: {e}")
                traceback.print_exc()
                return None
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
