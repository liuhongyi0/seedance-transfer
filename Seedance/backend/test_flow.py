#!/usr/bin/env python3
"""Seedance Studio 前端创作流程 API 联调"""
import aiohttp
import asyncio
import os
import random
import struct
import sys
import zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Seedance", "backend"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "Seedance", "backend", ".env"))

BASE = "http://127.0.0.1:8000"
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; N = "\033[0m"
ok = lambda m: print(f"{G}✅ {m}{N}")
fail = lambda m: print(f"{R}❌ {m}{N}")
warn = lambda m: print(f"{Y}⚠️  {m}{N}")

async def run():
    print("=" * 60)
    print("  Seedance Studio 前端创作流程 API 联调")
    print("=" * 60)

    async with aiohttp.ClientSession() as c:
        # 0. Health
        async with c.get(f"{BASE}/health") as r:
            data = await r.json()
        ok(f"Health: db={data['db']}, evolink={data['dependencies']['evolink']}")

        # 1. Register + topup
        email = f"flow{random.randint(1000,9999)}@seedance.test"
        async with c.post(f"{BASE}/api/auth/register", json={"email":email,"password":"flowtest123","auth_provider":"email"}) as r:
            token = (await r.json()).get("token", "")
        ok(f"注册: {email}")
        async with c.post(f"{BASE}/api/payment/test-topup", json={"amount_subunit":50000},
            headers={"Authorization": f"Bearer {token}"}) as r:
            bal = (await r.json()).get("new_balance_subunit", 0)
        ok(f"充值: {bal} fen")

        # 2. Session
        async with c.post(f"{BASE}/api/session/new", json={}) as r:
            sid = (await r.json()).get("session_id", "")
        ok(f"Session: {sid[:8]}...")

        # 3. Upload image
        print("\n--- Step 1: 图片上传 ---")
        def make_png():
            def chunk(t,d): c=t+d; return struct.pack('>I',len(d))+c+(struct.pack('>I',zlib.crc32(c)&0xffffffff))
            return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')
        form = aiohttp.FormData()
        form.add_field('file', make_png(), filename='test.png', content_type='image/png')
        async with c.post(f"{BASE}/api/upload/image", data=form,
            headers={"Authorization": f"Bearer {token}"}) as r:
            upload_data = await r.json()
            img_url = upload_data.get("url", "")
        ok(f"上传: {'OK' if img_url else 'FAIL (no url)'}")

        # 4. Wizard Analyze
        print("\n--- Step 2: AI 图片分析 ---")
        async with c.post(f"{BASE}/api/wizard/analyze", json={
            "image_url": img_url, "idea_text": "person walking on beach at sunset", "language": "zh"
        }, headers={"Authorization": f"Bearer {token}"}) as r:
            analyze = await r.json()
        if analyze.get("success"):
            ok(f"style={analyze.get('style','?')}, mood={analyze.get('mood','?')}")
        else:
            warn(f"分析: {str(analyze)[:100]}")

        # 5. Wizard Preview
        print("\n--- Step 3: 预览图 ---")
        async with c.post(f"{BASE}/api/wizard/preview", json={
            "style": analyze.get("style","cinematic"),
            "mood": analyze.get("mood","dramatic"),
            "color_palette": analyze.get("color_palette","warm"),
            "camera": analyze.get("camera","static"),
            "prompt_en": analyze.get("prompt_en","a cinematic sunset scene"),
            "aspect_ratio": "16:9"
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=120)) as r:
            preview = await r.json()
        preview_url = preview.get("preview_url","")
        if preview.get("success"):
            ok(f"preview: {'OK' if preview_url else 'no url yet (will retry)'}")
        else:
            warn(f"预览: {str(preview)[:100]}")

        # 6. Video Draft
        print("\n--- Step 4: 视频草稿 ---")
        async with c.post(f"{BASE}/api/video-draft/generate", json={
            "session_id": sid,
            "prompt_en": analyze.get("prompt_en","a cinematic scene, slow pan, warm sunset"),
            "resolution": "480p", "duration": 5
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=30)) as r:
            draft = await r.json()
        dtask = draft.get("task_id","")
        if dtask:
            ok(f"task_id={dtask[:8]}... status={draft.get('status','')}")
        else:
            fail(f"失败: {str(draft)[:150]}")

        # 7. Music
        print("\n--- Step 5: 音乐 ---")
        async with c.post(f"{BASE}/api/music/generate", json={
            "session_id": sid, "mood": "温柔舒缓", "genre": "纯钢琴", "duration": 30
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=30)) as r:
            music = await r.json()
        if music.get("success"):
            ok(f"task_id={music.get('task_id','')[:8]}... status={music.get('status','')}")
        else:
            fail(f"失败: {str(music)[:150]}")

        # 8. Final Video
        print("\n--- Step 6: 最终成片 ---")
        async with c.post(f"{BASE}/api/final-video/generate", json={
            "session_id": sid, "prompt_en": analyze.get("prompt_en","cinematic scene"),
            "resolution": "720p", "duration": 5, "aspect_ratio": "16:9"
        }, headers={"Authorization": f"Bearer {token}"}) as r:
            final = await r.json()
        if final.get("success"):
            ok(f"task_id={final.get('task_id','')[:8]}... cost_val={final.get('cost_val','?')}")
        else:
            warn(f"成片: {str(final)[:120]}")

        # 9. Model Catalog
        print("\n--- 模型目录 ---")
        for step in ["image","video_draft","music","final_video"]:
            async with c.get(f"{BASE}/api/models?step={step}") as r:
                data = await r.json()
            models = data.get("models",[])
            names = [m["key"] for m in models]
            print(f"  {step}: {len(models)} models -> {names}")

        # 10. Pricing
        print("\n--- 套餐定价 ---")
        async with c.get(f"{BASE}/api/payment/pricing") as r:
            prices = await r.json()
        pkg_names = [p["display"] for p in prices.get("packages",[])]
        ok(f"定价: {pkg_names}")

    print("\n" + "=" * 60)
    print("  前端 API 联调完成!")

asyncio.run(run())
