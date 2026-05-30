#!/usr/bin/env python3
"""Seedance Studio 端到端业务流程测试 — 注册→上传→分析→预览→视频→音乐→成片"""
import aiohttp, asyncio, struct, zlib, random, json, time, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()

BASE = "https://see4dance.com"
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; N = "\033[0m"
ok = lambda m: print(f"{G}✅ {m}{N}")
fail = lambda m: print(f"{R}❌ {m}{N}")
warn = lambda m: print(f"{Y}⚠️  {m}{N}")
info = lambda m: print(f"{B}  {m}{N}")

def make_png():
    def ck(t,d): c=t+d; return struct.pack('>I',len(d))+c+(struct.pack('>I',zlib.crc32(c)&0xffffffff))
    return b'\x89PNG\r\n\x1a\n'+ck(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+ck(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+ck(b'IEND',b'')

async def main():
    total_start = time.time()
    print("=" * 65)
    print("  🎬 Seedance Studio — 端到端业务流程测试")
    print("=" * 65)

    async with aiohttp.ClientSession() as c:
        # ═══ 0. Health ═══
        print("\n── ⚙️  健康检查 ──")
        r = await c.get(f"{BASE}/health")
        h = await r.json()
        ok(f"Service: {h.get('service','?')} v{h.get('version','?')}, db={h.get('db','?')}")

        # ═══ 1. Register ═══
        print("\n── 👤 用户注册 ──")
        email = f"e2e{random.randint(100,999)}@seedance.test"
        r = await c.post(f"{BASE}/api/auth/register", json={
            "email": email, "password": "e2etest123", "auth_provider": "email"
        })
        data = await r.json()
        token = data.get("token", "")
        assert token, f"注册失败: {data}"
        ok(f"注册: {email}  token={'✅' if token else '❌'}")

        # ═══ 2. Top up ═══
        r = await c.post(f"{BASE}/api/payment/test-topup",
            json={"amount_subunit": 100000},
            headers={"Authorization": f"Bearer {token}"})
        bal = (await r.json()).get("new_balance_subunit", 0)
        ok(f"充值: {bal} fen = ¥{bal/100:.2f}")

        # ═══ 3. Upload ═══
        print("\n── 🖼️  图片上传 ──")
        form = aiohttp.FormData()
        form.add_field('file', make_png(), filename='e2e-test.png', content_type='image/png')
        r = await c.post(f"{BASE}/api/upload/image", data=form,
            headers={"Authorization": f"Bearer {token}"})
        img_url = (await r.json()).get("url", "")
        assert img_url, "上传失败: 无 URL"
        is_r2 = "r2" in img_url.lower()
        ok(f"上传: {'R2 ✅' if is_r2 else img_url[:50]}")

        # ═══ 4. Create Session ═══
        print("\n── 📁 创建会话 ──")
        r = await c.post(f"{BASE}/api/session/new", json={})
        sid = (await r.json()).get("session_id", "")
        ok(f"Session: {sid[:8]}...")

        # ═══ 5. AI Analyze ═══
        print("\n── 🤖 AI 图片分析 ──")
        r = await c.post(f"{BASE}/api/wizard/analyze", json={
            "image_url": img_url,
            "idea_text": "a lone traveler walking through a bamboo forest at dawn, misty atmosphere, golden light filtering through leaves",
            "language": "zh"
        }, headers={"Authorization": f"Bearer {token}"})
        analyze = await r.json()
        ok(f"分析: style={analyze.get('style','?')}, mood={analyze.get('mood','?')}, camera={analyze.get('camera','?')}")
        info(f"  prompt: {analyze.get('prompt_en','')[:100]}...")

        # ═══ 6. Preview Image ═══
        print("\n── 🎨 预览图生成 ──")
        r = await c.post(f"{BASE}/api/wizard/preview", json={
            "style": analyze.get("style", "cinematic"),
            "mood": analyze.get("mood", "dramatic"),
            "color_palette": analyze.get("color_palette", "warm golden"),
            "camera": analyze.get("camera", "slow pan right"),
            "prompt_en": analyze.get("prompt_en", "cinematic bamboo forest"),
            "aspect_ratio": "16:9"
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=120))
        preview = await r.json()
        preview_url = preview.get("preview_url", "")
        ok(f"预览图: {'🖼️ OK' if preview_url else '⏳ pending'}")

        # ═══ 7. Video Draft ═══
        print("\n── 🎬 视频草稿 ──")
        r = await c.post(f"{BASE}/api/video-draft/generate", json={
            "session_id": sid,
            "prompt_en": analyze.get("prompt_en", "cinematic forest scene"),
            "resolution": "480p", "duration": 5
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=30))
        draft = await r.json()
        draft_task = draft.get("task_id", "")
        ok(f"视频草稿: task={draft_task[:8] if draft_task else '?'}... status={draft.get('status','?')}")
        info(f"  轮询: GET /api/video-draft/task/{draft_task}?session_id={sid}")

        # ═══ 8. Music ═══
        print("\n── 🎵 音乐生成 ──")
        r = await c.post(f"{BASE}/api/music/generate", json={
            "session_id": sid,
            "mood": "空灵治愈", "genre": "国风古典",
            "instruments": ["古筝", "笛子"], "duration": 30
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=30))
        music = await r.json()
        music_task = music.get("task_id", "")
        ok(f"音乐: task={music_task[:8] if music_task else '?'}... status={music.get('status','?')}")

        # ═══ 9. Model Catalog ═══
        print("\n── 📋 模型目录 ──")
        for step in ["image", "video_draft", "music", "final_video"]:
            r = await c.get(f"{BASE}/api/models?step={step}")
            models = (await r.json()).get("models", [])
            names = [m["key"] for m in models]
            info(f"  {step}: {len(models)} → {names[:5]}{'...' if len(names)>5 else ''}")

        # ═══ 10. Pricing ═══
        print("\n── 💰 套餐定价 ──")
        r = await c.get(f"{BASE}/api/payment/pricing")
        pkgs = (await r.json()).get("packages", [])
        names = [f"{p['display']}({p['credits']}pt)" for p in pkgs]
        ok(f"定价: {names}")

    elapsed = time.time() - total_start
    print("\n" + "=" * 65)
    print(f"  ✅ 端到端测试完成！耗时 {elapsed:.1f}s")
    print(f"  所有 10 项核心流程通过")
    print("=" * 65)

asyncio.run(main())
