"""
API Key 管理路由
GET    /api/keys          → 列出当前用户的 API Keys
POST   /api/keys          → 创建新 API Key（返回明文，仅此一次）
DELETE /api/keys/{key_id} → 撤销 API Key
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import hashlib
import secrets
import os

from store import store
from services.billing import require_user

router = APIRouter()

KEY_PREFIX = "sk-seed-"


def _create_key() -> tuple[str, str, str]:
    """返回 (plaintext, hash, key_id)"""
    key_id = secrets.token_hex(6)
    random = secrets.token_hex(10)
    plaintext = f"{KEY_PREFIX}{key_id}{random}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash, key_id


async def _get_user_id(request: Request) -> str:
    """从 JWT / API Key 提取 user_id"""
    user_id = await require_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


class CreateKeyRequest(BaseModel):
    name: str = ""


@router.get("")
async def list_keys(request: Request):
    user_id = await _get_user_id(request)
    keys = await store.get_api_keys(user_id)
    return {"success": True, "keys": keys}


@router.post("")
async def create_key(req: CreateKeyRequest, request: Request):
    user_id = await _get_user_id(request)
    plaintext, key_hash, key_id = _create_key()
    prefix = plaintext[:14] + "***"
    await store.create_api_key(user_id, key_id, key_hash, prefix, req.name or "")
    return {
        "success": True,
        "key": plaintext,
        "key_id": key_id,
        "key_prefix": prefix,
        "hint": "Store this key securely. It will NOT be shown again.",
    }


@router.delete("/{key_id}")
async def revoke_key(key_id: str, request: Request):
    user_id = await _get_user_id(request)
    ok = await store.revoke_api_key(user_id, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found or already revoked")
    return {"success": True, "detail": "API key revoked"}
