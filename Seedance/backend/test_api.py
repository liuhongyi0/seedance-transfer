#!/usr/bin/env python3
"""
Seedance Studio API 联调验证脚本
运行方式：python3 test_api.py
需要后端已启动：uvicorn main:app --port 8000
"""
import asyncio
import httpx
import sys
import os
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:8000"
EVOLINK_KEY = os.getenv("EVOLINK_API_KEY", "")
VOLC_KEY = os.getenv("VOLC_API_KEY", "")

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

ok = lambda msg: print(f"{GREEN}✅ {msg}{RESET}")
fail = lambda msg: print(f"{RED}❌ {msg}{RESET}")
warn = lambda msg: print(f"{YELLOW}⚠️  {msg}{RESET}")


async def test_backend_health(client):
    print("\n─── 1. 后端健康检查 ───")
    try:
        r = await client.get(f"{BASE}/health")
        if r.status_code == 200:
            ok(f"后端运行正常: {r.json()}")
        else:
            fail(f"health 返回 {r.status_code}")
    except Exception as e:
        fail(f"无法连接后端（是否已启动？）: {e}")
        sys.exit(1)


async def test_session(client):
    print("\n─── 2. Session 创建 ───")
    r = await client.post(f"{BASE}/api/session/new")
    assert r.status_code == 200, f"创建Session失败: {r.text}"
    sid = r.json()["session_id"]
    ok(f"Session创建成功: {sid[:8]}…")

    r2 = await client.get(f"{BASE}/api/session/{sid}")
    assert r2.status_code == 200
    ok(f"Session查询成功, 素材盘: {r2.json()['asset_counts']}")
    return sid


async def test_evolink_direct(client):
    print("\n─── 3. EvoLink API 直连测试 ───")
    if not EVOLINK_KEY:
        warn("EVOLINK_API_KEY 未配置，跳过")
        return False

    try:
        r = await client.get(
            "https://api.evolink.ai/v1/models",
            headers={"Authorization": f"Bearer {EVOLINK_KEY}"},
            timeout=15.0
        )
        if r.status_code == 200:
            data = r.json()
            models = [m["id"] for m in data.get("data", [])[:3]]
            ok(f"EvoLink连通，部分模型: {models}")
            return True
        else:
            fail(f"EvoLink返回 {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        fail(f"EvoLink连接失败: {e}")
        return False


async def test_image_generate(client, sid):
    print("\n─── 4. 步骤一：图片生成 ───")
    r = await client.post(f"{BASE}/api/image/generate", json={
        "session_id": sid,
        "prompt_cn": "樱花树下的女孩",
        "style": "电影质感",
        "lighting": "黄金时刻",
        "mood": "温暖治愈",
        "theme": "人物",
        "ratio": "16:9",
        "count": 1
    }, timeout=90.0)

    if r.status_code != 200:
        fail(f"图片生成请求失败 {r.status_code}: {r.text[:300]}")
        return None

    data = r.json()
    note = data.get("note", "")
    if "Mock" in note:
        warn(f"图片生成 → Mock模式（API Key未生效）: {data.get('images', [])[:1]}")
    else:
        ok(f"图片生成成功! 状态={data['status']}, 图片数={len(data.get('images',[]))}")
        if data.get("images"):
            ok(f"  第一张URL: {data['images'][0][:80]}…")
    return data


async def test_video_draft(client, sid):
    print("\n─── 5. 步骤三：视频草稿生成 ───")
    r = await client.post(f"{BASE}/api/video-draft/generate", json={
        "session_id": sid,
        "prompt_en": "A young woman in white dress, slowly turns around, gentle breeze, in a seaside at dusk, camera fixed, 35mm film tone, avoid jitter.",
        "resolution": "480p",
        "duration": 5
    }, timeout=150.0)

    if r.status_code != 200:
        fail(f"视频草稿请求失败 {r.status_code}: {r.text[:300]}")
        return None

    data = r.json()
    note = data.get("note", "")
    if "Mock" in str(note):
        warn(f"视频草稿 → Mock模式: {data.get('video_url','')[:60]}")
    else:
        ok(f"视频草稿提交成功! task_id={data.get('task_id','')[:8]}… status={data.get('status')}")
        if data.get("video_url"):
            ok(f"  视频URL: {data['video_url'][:80]}…")
    return data


async def test_music(client, sid):
    print("\n─── 6. 步骤四：音乐生成 ───")
    r = await client.post(f"{BASE}/api/music/generate", json={
        "session_id": sid,
        "mood": "温柔舒缓",
        "genre": "纯钢琴",
        "duration": 10
    }, timeout=90.0)

    if r.status_code != 200:
        fail(f"音乐生成请求失败 {r.status_code}: {r.text[:300]}")
        return

    data = r.json()
    warn(f"音乐生成（始终Mock）: status={data.get('status')}, url={str(data.get('audio_url',''))[:60]}")


async def test_volc_direct(client):
    print("\n─── 7. 火山引擎 API 直连测试 ───")
    if not VOLC_KEY:
        warn("VOLC_API_KEY 未配置，跳过")
        return False
    try:
        r = await client.get(
            "https://ark.cn-beijing.volces.com/api/v3/models",
            headers={"Authorization": f"Bearer {VOLC_KEY}"},
            timeout=15.0
        )
        if r.status_code == 200:
            ok(f"火山引擎连通! 返回: {str(r.json())[:100]}")
            return True
        elif r.status_code == 401:
            fail(f"火山引擎认证失败（Key可能有误）: {r.text[:200]}")
        else:
            warn(f"火山引擎返回 {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        fail(f"火山引擎连接失败: {e}")
        return False


# ─── 新增测试：认证 ─────────────────────────────────────────────────────────

async def test_register(client):
    print("\n─── 8. 用户注册 ───")
    test_email = f"test{os.urandom(2).hex()}@seedance.test"
    test_pass = "test12345678"
    r = await client.post(f"{BASE}/api/auth/register", json={
        "email": test_email,
        "password": test_pass,
        "auth_provider": "email"
    })
    if r.status_code == 200:
        data = r.json()
        ok(f"注册成功: user_id={data.get('user_id','')[:8]}… token={'OK' if data.get('token') else 'MISSING'}")
        return test_email, test_pass, data.get("token")
    elif r.status_code == 409:
        warn(f"用户已存在（可能之前测试残留）: {r.json().get('detail','')}")
        return None, None, None
    else:
        fail(f"注册失败 {r.status_code}: {r.text[:200]}")
        return None, None, None


async def test_login(client, email, password):
    print("\n─── 9. 用户登录 ───")
    if not email:
        warn("跳过（注册失败）")
        return None
    r = await client.post(f"{BASE}/api/auth/login", json={
        "email": email, "password": password
    })
    if r.status_code == 200:
        data = r.json()
        ok(f"登录成功: token={'OK' if data.get('token') else 'MISSING'}")
        return data.get("token")
    else:
        fail(f"登录失败 {r.status_code}: {r.text[:200]}")
        return None


async def test_auth_me(client, token):
    print("\n─── 10. 获取用户信息 ───")
    if not token:
        warn("跳过（无 token）")
        return
    r = await client.get(f"{BASE}/api/auth/me", headers={
        "Authorization": f"Bearer {token}"
    })
    if r.status_code == 200:
        data = r.json()
        user = data.get("user", {})
        ok(f"用户信息: email={user.get('email')}, balance={user.get('balance_subunit', 0)/100:.2f}")
    else:
        fail(f"获取失败 {r.status_code}: {r.text[:200]}")


# ─── 新增测试：支付 & API Keys ──────────────────────────────────────────────

async def test_pricing(client):
    print("\n─── 11. 套餐定价 ───")
    r = await client.get(f"{BASE}/api/payment/pricing")
    if r.status_code == 200:
        data = r.json()
        pkgs = data.get("packages", [])
        names = [p["display"] for p in pkgs]
        ok(f"定价获取成功: {names}")
    else:
        fail(f"定价获取失败 {r.status_code}: {r.text[:200]}")


async def test_api_keys(client, token):
    print("\n─── 12. API Key 管理 ───")
    if not token:
        warn("跳过（无 token）")
        return
    # List
    r = await client.get(f"{BASE}/api/keys", headers={
        "Authorization": f"Bearer {token}"
    })
    if r.status_code == 200:
        keys = r.json().get("keys", [])
        ok(f"API Keys: {len(keys)} 个")
    else:
        fail(f"获取失败 {r.status_code}: {r.text[:200]}")


# ─── 新增测试：最终成片 ────────────────────────────────────────────────────

async def test_final_video(client, sid):
    print("\n─── 13. 步骤五：最终成片 ───")
    r = await client.post(f"{BASE}/api/final-video/generate", json={
        "session_id": sid,
        "prompt_en": "A serene mountain lake at sunrise, gentle ripples, slow camera pan, cinematic lighting",
        "resolution": "720p",
        "duration": 5,
        "ratio": "16:9",
        "generate_audio": False
    }, timeout=120.0)
    if r.status_code != 200:
        fail(f"成片请求失败 {r.status_code}: {r.text[:300]}")
        return None
    data = r.json()
    note = data.get("note", "")
    if "Mock" in str(note):
        warn("最终成片 → Mock模式")
    else:
        ok(f"成片提交成功! task_id={data.get('task_id','')[:8]}… status={data.get('status')}")
    return data


# ─── 新增测试：SSE 任务轮询 ────────────────────────────────────────────────

async def test_sse_poll(client, sid, task_id, label):
    if not task_id:
        return
    print(f"\n─── {label}（轮询验证）───")
    # Poll via REST endpoint (SSE requires persistent connection)
    for attempt in range(10):
        await asyncio.sleep(2)
        try:
            r = await client.get(
                f"{BASE}/api/video-draft/task/{task_id}",
                params={"session_id": sid},
                timeout=10.0
            )
            if r.status_code != 200:
                continue
            data = r.json()
            st = data.get("status", "")
            if st in ("completed", "failed"):
                if st == "completed":
                    ok(f"任务完成: video_url={'OK' if data.get('video_url') else 'NONE'}")
                else:
                    warn(f"任务失败: {data.get('error', 'unknown')[:80]}")
                return
        except Exception:
            pass
    warn("轮询超时（任务可能仍在运行）")


# ─── 新增测试：ComfyUI Wizard ──────────────────────────────────────────────

async def test_wizard_balance(client):
    print("\n─── 14. Wizard 余额查询 ───")
    r = await client.get(f"{BASE}/api/balance")
    if r.status_code == 200:
        ok("余额接口正常")
    else:
        warn(f"余额接口返回 {r.status_code}（可能需要认证）")


async def test_wizard_estimate(client):
    print("\n─── 15. Wizard 费用预估 ───")
    r = await client.post(f"{BASE}/api/estimate", json={
        "duration": 5, "resolution": "720p", "prompt_en": "test video scene"
    })
    if r.status_code == 200:
        data = r.json()
        ok(f"费用预估: {data}")
    else:
        warn(f"预估接口返回 {r.status_code}: {r.text[:100]}")


# ─── 新增测试：Session 资产删除 ────────────────────────────────────────────

async def test_asset_delete(client, sid):
    print("\n─── 16. 素材盘删除操作 ───")
    # First add an image
    try:
        r = await client.post(f"{BASE}/api/image/generate", json={
            "session_id": sid,
            "prompt_cn": "test delete",
            "count": 1
        }, timeout=90.0)
        if r.status_code != 200:
            warn(f"无法生成测试图片: {r.status_code}")
            return
        data = r.json()
        # Save image to session assets
        images = data.get("images", [])
        if images:
            r2 = await client.post(f"{BASE}/api/image/save", json={
                "session_id": sid,
                "task_id": data.get("task_id", ""),
                "image_urls": images[:1]
            })
            if r2.status_code == 200:
                img_ids = r2.json().get("image_ids", [])
                if img_ids:
                    # Now delete it
                    r3 = await client.delete(f"{BASE}/api/session/{sid}/image/{img_ids[0]}")
                    if r3.status_code == 200:
                        ok(f"图片删除成功: {img_ids[0][:8]}…")
                    else:
                        fail(f"图片删除失败 {r3.status_code}: {r3.text[:100]}")
                else:
                    warn("保存成功但无 image_ids")
            else:
                warn(f"保存失败: {r2.status_code}")
    except Exception as e:
        fail(f"删除测试异常: {e}")


# ─── 新增测试：模型列表 ────────────────────────────────────────────────────

async def test_model_catalog(client):
    print("\n─── 17. 模型目录 ───")
    r = await client.get(f"{BASE}/api/models")
    if r.status_code == 200:
        data = r.json()
        cats = {k: len(v) for k, v in data.items()}
        ok(f"模型目录: {cats}")
    else:
        warn(f"模型目录返回 {r.status_code}")


# ─── 扩展测试：上传 ──────────────────────────────────────────────────

async def test_upload_image(client, token):
    print("\n─── 18. 图片上传 ───")
    if not token:
        warn("跳过（无 token）")
        return
    # Create a tiny valid PNG (1x1 pixel)
    import struct
    import zlib
    def make_png():
        def chunk(typ, data):
            c = typ + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00\x00')) + chunk(b'IEND', b'')
    png_data = make_png()
    files = {"file": ("test.png", png_data, "image/png")}
    r = await client.post(f"{BASE}/api/upload/image", files=files, headers={
        "Authorization": f"Bearer {token}"
    }, timeout=30.0)
    if r.status_code == 200:
        data = r.json()
        ok(f"上传成功: url={'OK' if data.get('url') else 'NONE'}")
    elif r.status_code == 422:
        warn(f"上传接口返回 422（可能缺少 imghost 配置）: {r.text[:100]}")
    else:
        warn(f"上传接口返回 {r.status_code}: {r.text[:100]}")


async def test_oauth_config(client):
    print("\n─── 19. OAuth 配置 ───")
    r = await client.get(f"{BASE}/api/auth/config")
    if r.status_code == 200:
        data = r.json()
        ok(f"OAuth配置: google={'SET' if data.get('google_client_id') else 'UNSET'}, github={'SET' if data.get('github_client_id') else 'UNSET'}")
    else:
        warn(f"OAuth配置返回 {r.status_code}")


async def test_video_draft_poll(client, sid):
    print("\n─── 20. 视频草稿任务查询（无 task_id）───")
    r = await client.get(f"{BASE}/api/video-draft/task/nonexistent", params={"session_id": sid})
    # Expect 404 or error response
    if r.status_code in (200, 404, 422):
        ok(f"任务查询返回 {r.status_code}（预期行为）")
    else:
        warn(f"任务查询返回 {r.status_code}")


async def test_final_video_cost(client):
    print("\n─── 21. 成片费用查询 ───")
    r = await client.get(f"{BASE}/api/final-video/cost", params={"duration": 5, "resolution": "720p"})
    if r.status_code == 200:
        ok(f"费用查询: {r.json()}")
    else:
        warn(f"费用查询返回 {r.status_code}")


async def test_payment_dashboard(client, token):
    print("\n─── 22. 支付 Dashboard ───")
    if not token:
        warn("跳过（无 token）")
        return
    r = await client.get(f"{BASE}/api/payment/dashboard", headers={
        "Authorization": f"Bearer {token}"
    })
    if r.status_code == 200:
        data = r.json()
        ok(f"Dashboard: balance={data.get('balance_subunit', 0)/100:.2f}")
    else:
        warn(f"Dashboard 返回 {r.status_code}")


async def test_api_key_create_delete(client, token):
    print("\n─── 23. API Key 创建 & 删除 ───")
    if not token:
        warn("跳过（无 token）")
        return
    # Create
    r = await client.post(f"{BASE}/api/keys", headers={
        "Authorization": f"Bearer {token}"
    }, json={"label": "test-key-auto"})
    if r.status_code == 200:
        data = r.json()
        kid = data.get("key_id") or data.get("id")
        ok(f"Key创建成功: id={str(kid)[:8]}…")
        # Delete it
        if kid:
            r2 = await client.delete(f"{BASE}/api/keys/{kid}", headers={
                "Authorization": f"Bearer {token}"
            })
            if r2.status_code == 200:
                ok("Key删除成功")
            else:
                warn(f"Key删除返回 {r2.status_code}")
    elif r.status_code == 501:
        warn("API Key 创建未实现（501）")
    else:
        warn(f"Key创建返回 {r.status_code}: {r.text[:100]}")


async def test_comfyui_activation(client):
    print("\n─── 24. ComfyUI 设备激活 ───")
    test_email = f"comfyui-{os.urandom(2).hex()}@seedance.test"
    r = await client.post(f"{BASE}/api/auth/comfyui/register", json={
        "email": test_email,
        "password": "test12345678",
        "device_id": f"test-device-{os.urandom(4).hex()}",
        "device_name": "Test ComfyUI Node"
    })
    if r.status_code == 200:
        data = r.json()
        code = data.get("activation_code", "")
        ok(f"设备注册成功: code={code[:8]}…")
        if code:
            r2 = await client.post(f"{BASE}/api/auth/comfyui/activate", json={
                "activation_code": code
            })
            if r2.status_code == 200:
                ok(f"设备激活成功: token={'OK' if r2.json().get('token') else 'NONE'}")
            else:
                warn(f"设备激活返回 {r2.status_code}")
    elif r.status_code == 501:
        warn("ComfyUI 激活未实现（501）")
    else:
        warn(f"设备注册返回 {r.status_code}: {r.text[:100]}")


async def main():
    print("=" * 55)
    print("  Seedance Studio API 联调验证")
    print("=" * 55)
    print(f"EVOLINK_API_KEY: {'已配置 (' + EVOLINK_KEY[:12] + '…)' if EVOLINK_KEY else '未配置'}")
    print(f"VOLC_API_KEY:    {'已配置 (' + VOLC_KEY[:12] + '…)' if VOLC_KEY else '未配置'}")

    async with httpx.AsyncClient() as client:
        # 基础测试
        await test_backend_health(client)
        sid = await test_session(client)
        await test_evolink_direct(client)

        # 核心流程
        img_data = await test_image_generate(client, sid)
        draft_data = await test_video_draft(client, sid)
        await test_music(client, sid)
        await test_volc_direct(client)

        # 新增：认证
        email, pwd, token = await test_register(client)
        token = await test_login(client, email, pwd) or token
        await test_auth_me(client, token)

        # 新增：支付 & Keys
        await test_pricing(client)
        await test_api_keys(client, token)

        # 新增：最终成片
        await test_final_video(client, sid)

        # 新增：Wizard
        await test_wizard_balance(client)
        await test_wizard_estimate(client)

        # 新增：任务轮询
        if draft_data and draft_data.get("task_id"):
            await test_sse_poll(client, sid, draft_data["task_id"], "视频草稿轮询")

        # 新增：素材删除
        await test_asset_delete(client, sid)

        # 新增：模型目录
        await test_model_catalog(client)

        # 扩展测试
        await test_upload_image(client, token)
        await test_oauth_config(client)
        await test_video_draft_poll(client, sid)
        await test_final_video_cost(client)
        await test_payment_dashboard(client, token)
        await test_api_key_create_delete(client, token)
        await test_comfyui_activation(client)

    print("\n" + "=" * 55)
    print("  验证完成。查看上方 ✅❌⚠️ 结果。")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
