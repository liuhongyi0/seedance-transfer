#!/usr/bin/env python3
"""EvoLink 三端点验证"""
import aiohttp
import asyncio
import os
import json
import random
import sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

BASE = "http://127.0.0.1:8000"
GREEN = "\033[92m"; RED = "\033[91m"; RESET = "\033[0m"
ok = lambda m: print(f"{GREEN}✅ {m}{RESET}")
fail = lambda m: print(f"{RED}❌ {m}{RESET}")

async def main():
    print("=" * 55)
    print("  EvoLink 三端点验证")
    print("=" * 55)

    async with aiohttp.ClientSession() as c:
        # 1. Health
        async with c.get(f"{BASE}/health") as r:
            data = await r.json()
            ok(f"健康检查: db={data['db']}, evolink={data['dependencies']['evolink']}")

        # 2. Register
        email = f"test{random.randint(1000,9999)}@seedance.test"
        async with c.post(f"{BASE}/api/auth/register", json={"email": email, "password": "test12345678", "auth_provider": "email"}) as r:
            token = (await r.json()).get("token", "")
        ok(f"注册: {'OK' if token else 'FAIL'}")

        # 3. Session
        async with c.post(f"{BASE}/api/session/new", json={}) as r:
            sid = (await r.json()).get("session_id", "")
        ok(f"Session: {sid[:8] if sid else 'FAIL'}…")

        # 4. Top up test credits
        async with c.post(f"{BASE}/api/payment/test-topup",
            json={"amount_subunit": 10000, "tx_type": "test_topup"},
            headers={"Authorization": f"Bearer {token}"}) as r:
            topup = await r.json()
        ok(f"充值: {topup.get('new_balance_subunit', '?')} fen")

        # 5. Image
        print("\n─── 图片生成 ───")
        async with c.post(f"{BASE}/api/image/generate", json={
            "session_id": sid, "prompt_cn": "sunset over mountains", "count": 1
        }, timeout=aiohttp.ClientTimeout(total=120)) as r:
            txt = await r.text()
            if r.status == 200:
                data = json.loads(txt)
                ok(f"task_id={data.get('task_id','')[:8]}… status={data.get('status','')}")
            else:
                fail(f"{r.status}: {txt[:150]}")

        # 5. Video draft
        print("\n─── 视频草稿 ───")
        async with c.post(f"{BASE}/api/video-draft/generate", json={
            "session_id": sid, "prompt_en": "a person walking through a forest, cinematic",
            "resolution": "480p", "duration": 5
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=60)) as r:
            txt = await r.text()
            if r.status == 200:
                data = json.loads(txt)
                ok(f"task_id={data.get('task_id','')[:8]}… status={data.get('status','')}")
            else:
                fail(f"{r.status}: {txt[:200]}")

        # 6. Music
        print("\n─── 音乐生成 ───")
        async with c.post(f"{BASE}/api/music/generate", json={
            "session_id": sid, "mood": "温柔舒缓", "genre": "纯钢琴", "duration": 30
        }, headers={"Authorization": f"Bearer {token}"}, timeout=aiohttp.ClientTimeout(total=60)) as r:
            txt = await r.text()
            if r.status == 200:
                data = json.loads(txt)
                ok(f"task_id={data.get('task_id','')[:8]}… status={data.get('status','')}")
            else:
                fail(f"{r.status}: {txt[:200]}")

    print("\n" + "=" * 55)
    print("  验证完成")

asyncio.run(main())
