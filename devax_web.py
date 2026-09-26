#!/usr/bin/env python3
"""
devax_web.py — DEVA💗WINE Strike Tool · Web UI
Railway: Docker deploy — Dockerfile use karo
"""

import asyncio, logging, os, random, shutil, threading
from urllib.parse import unquote

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("devax")

PORT = int(os.getenv("PORT", 5000))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "deva-wine-key")

# ── DEFAULTS ──────────────────────────────────────────────────────────────────
DEFAULT_SID      = ""
DEFAULT_URL      = "https://www.instagram.com/direct/t/1704768377345706/"
DEFAULT_OPPONENT = "hater/bkl"
DEFAULT_GC       = "[{opponent}] की मां चुदके पागल"

_messages: list[str] = [
    "[{target}]--सिस्टम--𝑯ʏᴘᴇʀʟᴏᴀᴅ तेरी औकात नहीं--𝑴ᴇʀsᴇ--लड़ने--𝑲ɪ--😹🥀",
    "[{target}] 𝑻ᴜᴍʜᴀʀɪ--माईया--𝑲ᴏ 𝑪ʜᴏᴅ 𝑫ᴀᴀʟᴇɴɢᴇ //~🍑🍌",
    "[{target}]-𝑻ᴇʀɪ--माईया--𝑲ᴏ 𝑲ɪɴɴᴇʀ--ग्रुप--𝑾ᴀʟᴇ 𝑪ʜᴏᴅᴇɴɢᴇ--𝑫ᴏɢɢʏ(🐕)𝑺ᴛʏʟᴇ 👾💦",
    "[{target}]-𝑪ʜᴀᴍᴀʀ-𝑻ᴇʀɪ-माईया ᴋᴀ 𝘽𝙃𝙊𝙎𝘿𝘼⍟ --मै--𝑰ᴛɴᴇ 𝑪ʜᴀɴᴛᴇ(👋🏻)--मरूंगा 🐕💨",
    "[{target}] 𝐃єνα~//(🦂) 𝑶ᴘᴇʀᴀᴛɪɴɢ अब--𝑹ɴᴅʏ--रोना(💦)--𝑲ᴇ--अलावा कोई रास्ता नहीं😹🥀",
]

# ── STATE ─────────────────────────────────────────────────────────────────────
_stop_flag  = threading.Event()
_state_lock = threading.Lock()
_state = {
    "running": False,
    "engines": {},
    "total": 0,
    "url": "",
    "error": "",
    "sid_status": {},   # eid -> "ok" / "invalid" / "checking"
}
_form  = {
    "sids": DEFAULT_SID,
    "url": DEFAULT_URL,
    "opponent": DEFAULT_OPPONENT,
    "engine_count": "2",
    "delay": "0.3",
    "lock_enabled": True,
}

def _inc(eid: int):
    with _state_lock:
        _state["engines"][eid] = _state["engines"].get(eid, 0) + 1
        _state["total"] = sum(_state["engines"].values())

def _set_sid_status(eid: int, status: str):
    with _state_lock:
        _state["sid_status"][eid] = status

# ── PLAYWRIGHT ────────────────────────────────────────────────────────────────
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--single-process",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-extensions",
]

# Real browser headers — Instagram ke liye
IG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36 Instagram/313.0.0.0"
    ),
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

async def _block_media(route):
    if route.request.resource_type in ("image", "media", "font", "stylesheet"):
        await route.abort()
    else:
        await route.continue_()

async def _check_session(page) -> bool:
    """
    Session valid hai ya nahi — IG login page check karta hai.
    Returns True agar logged in, False agar session dead.
    """
    try:
        current = page.url
        # Agar redirect ho gaya login pe
        if "accounts/login" in current or "accounts/suspended" in current:
            return False
        # Logged-in user ka userId meta ya cookies check
        cookies = await page.context.cookies()
        sid_cookie = next((c for c in cookies if c["name"] == "sessionid"), None)
        if not sid_cookie:
            return False
        # DM page pe koi "Log in" button hai toh session dead
        login_btn = page.locator('a[href*="/accounts/login/"]')
        if await login_btn.count() > 0:
            return False
        return True
    except Exception as e:
        log.warning("session_check error: %s", e)
        return False

async def _force_lock(page, gc_name: str):
    try:
        gear = page.locator('svg[aria-label="Conversation information"]')
        await gear.click()
        await page.locator('div[aria-label="Change group name"][role="button"]').click()
        inp = page.locator('input[aria-label="Group name"][name="change-group-name"]')
        await inp.fill(gc_name)
        save = page.locator('div[role="button"]:has-text("Save")')
        if await save.is_enabled():
            await save.click()
        await gear.click()
    except Exception as e:
        log.warning("lock: %s", e)
        await page.reload(wait_until="domcontentloaded")

def _payload(opponent: str) -> str:
    gap  = "\n" * 160
    core = random.choice(_messages).replace("{target}", opponent)
    return f"{core}{gap}{core}{gap}{core}\n🔱DEVA💗WINE [{random.randint(1000,9999)}] 🔱"

async def _engine(eid: int, sid: str, url: str, gc_name: str,
                  opponent: str, is_locker: bool, delay: float):
    udd = f"/tmp/deva_{eid}"
    _set_sid_status(eid, "checking")

    while not _stop_flag.is_set():
        async with async_playwright() as p:
            try:
                ctx = await p.chromium.launch_persistent_context(
                    udd,
                    headless=True,
                    args=BROWSER_ARGS,
                    user_agent=IG_HEADERS["User-Agent"],
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=3,
                    is_mobile=True,
                    has_touch=True,
                )
            except Exception as le:
                log.error("E-%d LAUNCH FAILED: %s", eid, le)
                _set_sid_status(eid, "launch_fail")
                await asyncio.sleep(5)
                continue

            # Extra headers set karo
            await ctx.set_extra_http_headers({
                "Accept-Language": IG_HEADERS["Accept-Language"],
                "sec-ch-ua": IG_HEADERS["sec-ch-ua"],
                "sec-ch-ua-mobile": IG_HEADERS["sec-ch-ua-mobile"],
                "sec-ch-ua-platform": IG_HEADERS["sec-ch-ua-platform"],
            })

            # Session cookie inject
            await ctx.add_cookies([{
                "name": "sessionid",
                "value": unquote(sid.strip()),
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            }])

            page = await ctx.new_page()
            await page.route("**/*", _block_media)

            try:
                # ── SESSION VALIDITY CHECK ────────────────────────────────
                log.info("E-%d: Session check kar raha hun...", eid)
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(2000)  # JS settle hone do

                session_ok = await _check_session(page)
                if not session_ok:
                    log.warning("E-%d: SESSION INVALID/EXPIRED — skip", eid)
                    _set_sid_status(eid, "invalid")
                    await ctx.close()
                    shutil.rmtree(udd, ignore_errors=True)
                    return  # Is engine ko band karo, SID dead hai

                log.info("E-%d: Session OK — strike shuru", eid)
                _set_sid_status(eid, "ok")

                # ── DM URL PE JAO ─────────────────────────────────────────
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Textbox milne ka wait
                try:
                    await page.wait_for_selector(
                        'div[role="textbox"], div[aria-label="Message"]',
                        timeout=30000,
                    )
                except Exception:
                    log.warning("E-%d: Textbox nahi mila — reload try", eid)
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                box = page.locator('div[role="textbox"],div[aria-label="Message"]').first
                mc  = 0

                for _ in range(150):
                    if _stop_flag.is_set():
                        break

                    if mc > 0 and mc % 30 == 0:
                        await page.reload(wait_until="domcontentloaded")
                        await page.wait_for_timeout(2000)
                        box = page.locator('div[role="textbox"],div[aria-label="Message"]').first
                        await box.focus()

                    if is_locker and mc >= 19:
                        await _force_lock(page, gc_name)
                        mc = 0
                        await box.focus()

                    await box.focus()
                    await box.fill(_payload(opponent))
                    await page.keyboard.press("Enter")
                    mc += 1
                    _inc(eid)
                    await asyncio.sleep(random.uniform(delay, delay + 0.15))

            except Exception as e:
                log.warning("E-%d runtime: %s", eid, e)
            finally:
                await ctx.close()
                shutil.rmtree(udd, ignore_errors=True)

        if not _stop_flag.is_set():
            await asyncio.sleep(2)

async def _main(sids, url, gc_name, opponent, n, delay):
    await asyncio.gather(*[
        _engine(i+1, sids[i % len(sids)], url, gc_name, opponent, i == 0, delay)
        for i in range(n)
    ])

def _runner(sids, url, gc_name, opponent, n, delay):
    try:
        asyncio.run(_main(sids, url, gc_name, opponent, n, delay))
    except Exception as e:
        with _state_lock:
            _state["error"] = str(e)
    finally:
        with _state_lock:
            _state["running"] = False

def start_strike(sids, url, gc_name, opponent, n, delay):
    if _state["running"]:
        return "Pehle se chal raha hai."
    _stop_flag.clear()
    with _state_lock:
        _state.update({
            "running": True, "engines": {}, "total": 0,
            "url": url, "error": "", "sid_status": {},
        })
    threading.Thread(
        target=_runner, args=(sids, url, gc_name, opponent, n, delay), daemon=True
    ).start()
    return None

def stop_strike():
    _stop_flag.set()
    with _state_lock:
        _state["running"] = False

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DEVA💗WINE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0d0608;--paper:#100509;--layer1:#180a0e;--layer2:#200d12;--layer3:#2a1018;
  --rim:#3d1622;--rim2:#5c1f30;--wine:#8b1a3a;--wine2:#b02249;--rose:#d4496a;
  --blush:#e8809a;--petal:#f2b8c6;--cream:#f7e8ed;--txt:#f0dce4;--txt2:#c4919f;
  --txt3:#7a4455;--glow-wine:rgba(176,34,73,0.18);--glow-rose:rgba(212,73,106,0.22);
}
html,body{min-height:100vh;background:var(--paper);color:var(--txt);font-family:'Cormorant Garamond',Georgia,serif;}
body{
  background-image:
    radial-gradient(ellipse 70% 55% at 50% -10%,rgba(139,26,58,0.25),transparent),
    radial-gradient(ellipse 40% 30% at 90% 60%,rgba(176,34,73,0.08),transparent);
  padding:36px 16px 100px;
}
.wrap{max-width:520px;margin:0 auto}
.hero{text-align:center;padding:44px 24px 38px;position:relative;margin-bottom:6px;}
.hero::after{content:'';display:block;width:140px;height:1px;margin:22px auto 0;background:linear-gradient(90deg,transparent,var(--wine2),transparent);}
.hero-eyebrow{font-family:'DM Mono',monospace;font-size:.6rem;letter-spacing:.3em;color:var(--txt3);margin-bottom:20px;font-weight:300;}
.hero-name{font-size:3.6rem;font-weight:300;font-style:italic;letter-spacing:.04em;line-height:1;color:var(--cream);text-shadow:0 0 60px rgba(212,73,106,0.4),0 2px 4px rgba(0,0,0,0.5);margin-bottom:6px;}
.hero-heart{font-size:2.8rem;line-height:1;filter:drop-shadow(0 0 12px rgba(212,73,106,0.7));display:inline-block;animation:heartbeat 2.4s ease-in-out infinite;}
@keyframes heartbeat{0%,100%{transform:scale(1)}14%{transform:scale(1.12)}28%{transform:scale(1)}42%{transform:scale(1.06)}56%{transform:scale(1)}}
.hero-sub{font-family:'DM Mono',monospace;font-size:.58rem;letter-spacing:.2em;color:var(--txt3);margin-top:14px;font-weight:300;}
.status-pill{display:inline-flex;align-items:center;gap:7px;margin-top:18px;padding:6px 18px;border:1px solid var(--rim2);border-radius:100px;background:rgba(139,26,58,0.12);font-family:'DM Mono',monospace;font-size:.58rem;letter-spacing:.15em;color:var(--blush);}
.status-pill::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--rose);box-shadow:0 0 6px var(--rose);}
.card{background:var(--layer1);border:1px solid var(--rim);border-radius:14px;padding:22px 20px;margin-bottom:10px;position:relative;overflow:hidden;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(212,73,106,0.35),transparent);}
.card-label{font-family:'DM Mono',monospace;font-size:.55rem;letter-spacing:.2em;color:var(--txt3);margin-bottom:18px;font-weight:400;display:flex;align-items:center;gap:8px;}
.card-label::before{content:'';display:block;width:14px;height:1px;background:var(--wine2);}
.field{margin-bottom:14px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
label{display:block;font-family:'DM Mono',monospace;font-size:.57rem;letter-spacing:.14em;color:var(--txt3);margin-bottom:8px;font-weight:300;}
input[type=text],input[type=number],textarea{width:100%;background:var(--ink);border:1px solid var(--rim);border-radius:9px;padding:11px 13px;color:var(--txt);font-size:.88rem;font-family:'Cormorant Garamond',serif;font-weight:300;outline:none;transition:border-color .2s,box-shadow .2s;resize:vertical;}
input::placeholder,textarea::placeholder{color:var(--txt3);font-style:italic}
input:focus,textarea:focus{border-color:var(--wine2);box-shadow:0 0 0 3px var(--glow-wine),0 0 24px var(--glow-wine);}
textarea{min-height:72px}
.tog-row{display:flex;align-items:center;justify-content:space-between;padding:12px 0 4px;border-top:1px solid var(--rim);margin-top:6px;}
.tog-left .lbl{font-size:.9rem;color:var(--txt);font-weight:300;font-style:italic}
.tog-left .sub{font-size:.6rem;color:var(--txt3);margin-top:3px;font-family:'DM Mono',monospace;letter-spacing:.08em;font-weight:300;}
.switch{position:relative;width:40px;height:22px;flex-shrink:0}
.switch input{opacity:0;width:0;height:0}
.track{position:absolute;inset:0;background:var(--layer3);border:1px solid var(--rim2);border-radius:22px;cursor:pointer;transition:background .25s,box-shadow .25s;}
.track::before{content:'';position:absolute;width:15px;height:15px;left:3px;top:3px;background:var(--txt3);border-radius:50%;transition:transform .25s,background .25s;}
.switch input:checked + .track{background:var(--wine);border-color:var(--wine2);box-shadow:0 0 12px var(--glow-wine);}
.switch input:checked + .track::before{transform:translateX(18px);background:var(--petal);}
.msg-wrap{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.msg-row{display:flex;align-items:flex-start;gap:9px;padding:10px 12px;background:var(--ink);border:1px solid var(--rim);border-radius:9px;}
.msg-num{font-family:'DM Mono',monospace;font-size:.58rem;color:var(--wine2);min-width:16px;margin-top:2px;font-weight:500;flex-shrink:0;}
.msg-txt{flex:1;font-size:.8rem;color:var(--txt2);line-height:1.55;word-break:break-all;font-style:italic}
.del{background:none;border:none;color:var(--txt3);cursor:pointer;font-size:.75rem;padding:0 2px;flex-shrink:0;transition:color .15s;font-family:'DM Mono',monospace;}
.del:hover{color:var(--rose)}
.add-area{background:var(--ink);border:1px solid var(--rim);border-radius:9px;padding:11px 13px;color:var(--txt);font-size:.85rem;font-family:'Cormorant Garamond',serif;font-style:italic;width:100%;resize:none;outline:none;min-height:60px;transition:border-color .2s,box-shadow .2s;}
.add-area:focus{border-color:var(--wine2);box-shadow:0 0 0 3px var(--glow-wine)}
.add-area::placeholder{color:var(--txt3)}
.btn-add{margin-top:8px;background:transparent;border:1px solid var(--rim2);border-radius:8px;padding:8px 18px;color:var(--txt3);font-size:.7rem;cursor:pointer;font-family:'DM Mono',monospace;letter-spacing:.1em;transition:border-color .15s,color .15s;}
.btn-add:hover{border-color:var(--rose);color:var(--blush)}
.btn-check{width:100%;background:transparent;border:1px solid var(--rim2);border-radius:10px;padding:12px;color:var(--blush);font-size:.85rem;font-style:italic;font-family:'Cormorant Garamond',serif;cursor:pointer;letter-spacing:.06em;margin-bottom:10px;transition:border-color .2s,color .2s;}
.btn-check:hover{border-color:var(--rose);color:var(--petal)}
.btn-deploy{width:100%;background:linear-gradient(135deg,var(--wine) 0%,var(--wine2) 55%,var(--rose) 100%);border:none;border-radius:12px;padding:16px;color:var(--cream);font-size:1rem;font-weight:300;font-style:italic;font-family:'Cormorant Garamond',serif;cursor:pointer;letter-spacing:.08em;position:relative;overflow:hidden;transition:transform .1s,box-shadow .25s;box-shadow:0 4px 24px rgba(139,26,58,0.4);}
.btn-deploy:hover{transform:translateY(-1px);box-shadow:0 8px 32px rgba(176,34,73,.5);}
.btn-deploy:active{transform:translateY(0) scale(.99)}
.btn-stop{width:100%;background:linear-gradient(135deg,#3d0a10 0%,#7a1020 55%,#9e1428 100%);border:1px solid var(--rim2);border-radius:12px;padding:16px;color:var(--petal);font-size:1rem;font-weight:300;font-style:italic;font-family:'Cormorant Garamond',serif;cursor:pointer;letter-spacing:.08em;transition:transform .1s,box-shadow .25s;box-shadow:0 4px 20px rgba(100,10,20,0.4);}
.btn-stop:hover{transform:translateY(-1px)}
.btn-stop:active{transform:translateY(0) scale(.99)}
.alert{padding:12px 16px;border-radius:10px;font-size:.82rem;margin-bottom:14px;line-height:1.6;font-family:'DM Mono',monospace;font-weight:300;}
.alert.err{background:rgba(100,10,20,.1);border:1px solid rgba(158,20,40,.3);color:var(--blush);}
.alert.info{background:rgba(26,58,139,.1);border:1px solid rgba(34,73,176,.3);color:#8ab5e8;}
/* SID status badges */
.sid-status-wrap{margin-top:10px;display:flex;flex-direction:column;gap:6px;}
.sid-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:8px;font-family:'DM Mono',monospace;font-size:.58rem;letter-spacing:.1em;}
.sid-badge.ok{background:rgba(20,80,30,.2);border:1px solid rgba(40,140,60,.3);color:#6dd48a;}
.sid-badge.invalid{background:rgba(100,10,20,.15);border:1px solid rgba(158,20,40,.3);color:var(--blush);}
.sid-badge.checking{background:rgba(100,80,10,.1);border:1px solid rgba(160,130,20,.3);color:#d4b86a;animation:blink 1.2s ease-in-out infinite;}
.sid-badge.launch_fail{background:rgba(80,10,10,.2);border:1px solid rgba(140,20,20,.3);color:#e08080;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.5}}
.sid-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.sid-dot.ok{background:#6dd48a}
.sid-dot.invalid{background:var(--rose)}
.sid-dot.checking{background:#d4b86a}
.sid-dot.launch_fail{background:#e08080}
/* Live dashboard */
.live{position:relative;overflow:hidden;background:var(--layer1);border:1px solid var(--rim2);border-radius:18px;padding:32px 24px;margin-bottom:12px;}
.live::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(176,34,73,.14),transparent 65%);pointer-events:none;}
.live-hdr{display:flex;align-items:center;gap:10px;margin-bottom:24px;}
.pulse-dot{position:relative;width:10px;height:10px;flex-shrink:0;}
.pulse-dot::before{content:'';position:absolute;inset:0;border-radius:50%;background:var(--rose);}
.pulse-dot::after{content:'';position:absolute;inset:-4px;border-radius:50%;border:1.5px solid var(--rose);animation:pulse-out 1.8s ease-out infinite;opacity:0;}
@keyframes pulse-out{0%{transform:scale(0.6);opacity:.8}100%{transform:scale(2);opacity:0}}
.live-lbl{font-size:.72rem;letter-spacing:.2em;color:var(--blush);font-family:'DM Mono',monospace;font-weight:300;}
.big-counter{text-align:center;font-family:'Cormorant Garamond',serif;font-size:5.5rem;font-weight:300;font-style:italic;color:var(--petal);line-height:1;text-shadow:0 0 40px rgba(232,128,154,.35);margin-bottom:4px;}
.big-label{font-size:.58rem;color:var(--txt3);text-align:center;letter-spacing:.22em;font-family:'DM Mono',monospace;font-weight:300;margin-bottom:26px;}
.eng-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;}
.eng-card{background:rgba(0,0,0,.3);border:1px solid var(--rim);border-radius:10px;padding:14px;text-align:center;}
.eng-val{font-size:1.5rem;font-weight:300;font-style:italic;color:var(--blush);font-family:'Cormorant Garamond',serif;}
.eng-key{font-size:.55rem;color:var(--txt3);letter-spacing:.12em;margin-top:4px;font-family:'DM Mono',monospace;font-weight:300;}
.eng-status{font-size:.5rem;letter-spacing:.08em;margin-top:4px;font-family:'DM Mono',monospace;}
.eng-status.ok{color:#6dd48a}
.eng-status.invalid{color:var(--rose)}
.eng-status.checking{color:#d4b86a}
.eng-status.launch_fail{color:#e08080}
</style>
</head>
<body>
<div class="wrap">

<div class="hero">
  <div class="hero-eyebrow">strike system · railway edition</div>
  <div class="hero-name">DEVA</div>
  <div class="hero-heart">💗</div>
  <div class="hero-name">WINE</div>
  <div class="hero-sub">by DEVAXWINE · wine drinker</div>
  <div><span class="status-pill">target injection engine</span></div>
</div>

{% if error %}<div class="alert err">{{ error }}</div>{% endif %}

{% if state.running %}

<div class="live">
  <div class="live-hdr">
    <div class="pulse-dot"></div>
    <span class="live-lbl">engines active</span>
  </div>
  <div class="big-counter" id="total">{{ state.total }}</div>
  <div class="big-label">strikes delivered</div>
  <div class="eng-grid" id="eng-grid">
    {% for eid, cnt in state.engines.items() %}
    <div class="eng-card">
      <div class="eng-val">{{ cnt }}</div>
      <div class="eng-key">engine {{ eid }}</div>
      {% set st = state.sid_status.get(eid, 'checking') %}
      <div class="eng-status {{ st }}">{{ st }}</div>
    </div>
    {% endfor %}
  </div>
</div>

<form method="post" action="/stop">
  <button class="btn-stop" type="submit">⬛ &nbsp;terminate all engines</button>
</form>

{% else %}

<form method="post" action="/check" id="cf">
  <div class="card">
    <div class="card-label">session config</div>
    <div class="field">
      <label>session id(s) — comma se multiple</label>
      <textarea name="sids" rows="3" placeholder="SID1, SID2 ...">{{ form.sids }}</textarea>
    </div>
    {% if sid_results %}
    <div class="sid-status-wrap">
      {% for item in sid_results %}
      <div class="sid-badge {{ item.status }}">
        <div class="sid-dot {{ item.status }}"></div>
        <span>SID {{ loop.index }}: {{ item.status.upper() }}
          {% if item.username %} — @{{ item.username }}{% endif %}
        </span>
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
  <button class="btn-check" type="submit">🔍 &nbsp;session check karo</button>
</form>

<form method="post" action="/start" id="mf">

  <div class="card">
    <div class="card-label">session — strike ke liye</div>
    <div class="field">
      <label>session id(s)</label>
      <textarea name="sids" rows="3" placeholder="SID1, SID2 ...">{{ form.sids }}</textarea>
    </div>
  </div>

  <div class="card">
    <div class="card-label">target config</div>
    <div class="field">
      <label>group url</label>
      <input type="text" name="url" placeholder="https://www.instagram.com/direct/t/..." value="{{ form.url }}">
    </div>
    <div class="field">
      <label>opponent name</label>
      <input type="text" name="opponent" placeholder="e.g. CHUNKI/CHUDARA" value="{{ form.opponent }}">
    </div>
  </div>

  <div class="card">
    <div class="card-label">engine config</div>
    <div class="g2">
      <div class="field">
        <label>engine count</label>
        <input type="number" name="engine_count" min="1" max="4" value="{{ form.engine_count }}">
      </div>
      <div class="field">
        <label>delay (sec)</label>
        <input type="number" name="delay" min="0.1" max="5" step="0.1" value="{{ form.delay }}">
      </div>
    </div>
    <div class="tog-row">
      <div class="tog-left">
        <div class="lbl">Name Lock</div>
        <div class="sub">engine-1 group naam auto-reset karega</div>
      </div>
      <label class="switch" style="margin-left:12px">
        <input type="checkbox" name="lock_enabled" {% if form.lock_enabled %}checked{% endif %}>
        <span class="track"></span>
      </label>
    </div>
  </div>

  <div class="card">
    <div class="card-label">strike messages</div>
    <div class="msg-wrap">
      {% for msg in messages %}
      <div class="msg-row">
        <span class="msg-num">{{ loop.index }}</span>
        <span class="msg-txt">{{ msg }}</span>
        <form method="post" action="/msg/del" style="display:inline">
          <input type="hidden" name="idx" value="{{ loop.index0 }}">
          <button class="del" type="submit">✕</button>
        </form>
      </div>
      {% endfor %}
    </div>
    <textarea class="add-area" id="na" placeholder="naya message likho ..."></textarea>
    <button class="btn-add" type="button" id="ab">+ add message</button>
  </div>

  <button class="btn-deploy" type="submit">🔱 &nbsp;deploy engines</button>

</form>

<form id="af" method="post" action="/msg/add" style="display:none">
  <input type="hidden" name="text" id="av">
</form>

{% endif %}
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
  var ab = document.getElementById('ab');
  if (ab) {
    ab.addEventListener('click', function() {
      var ta = document.getElementById('na');
      if (!ta || !ta.value.trim()) return;
      document.getElementById('av').value = ta.value.trim();
      document.getElementById('af').submit();
    });
  }
});

{% if state.running %}
function poll() {
  fetch('/api/status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var t = document.getElementById('total');
      if (t) t.textContent = d.total;
      var g = document.getElementById('eng-grid');
      if (g && d.engines) {
        var ss = d.sid_status || {};
        g.innerHTML = Object.entries(d.engines).map(function(e) {
          var eid = e[0], cnt = e[1];
          var st = ss[eid] || 'checking';
          return '<div class="eng-card">' +
            '<div class="eng-val">' + cnt + '</div>' +
            '<div class="eng-key">engine ' + eid + '</div>' +
            '<div class="eng-status ' + st + '">' + st + '</div>' +
            '</div>';
        }).join('');
      }
      if (!d.running) setTimeout(function() { location.reload(); }, 800);
    }).catch(function() {});
}
setInterval(poll, 1500);
{% endif %}
</script>
</body>
</html>"""

# ── SESSION CHECK ROUTE ────────────────────────────────────────────────────────
async def _quick_session_check(sid: str) -> dict:
    """Single SID ko quickly check karta hai bina full engine chalaye."""
    udd = f"/tmp/check_{random.randint(10000,99999)}"
    result = {"status": "invalid", "username": None}
    try:
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                udd, headless=True, args=BROWSER_ARGS,
                user_agent=IG_HEADERS["User-Agent"],
                locale="en-US",
                viewport={"width": 390, "height": 844},
                is_mobile=True, has_touch=True,
            )
            await ctx.add_cookies([{
                "name": "sessionid", "value": unquote(sid.strip()),
                "domain": ".instagram.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "Lax",
            }])
            page = await ctx.new_page()
            await page.route("**/*", _block_media)
            try:
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)

                if "accounts/login" in page.url or "accounts/suspended" in page.url:
                    result["status"] = "invalid"
                else:
                    cookies = await ctx.cookies()
                    has_sid = any(c["name"] == "sessionid" for c in cookies)
                    login_btn = page.locator('a[href*="/accounts/login/"]')
                    if has_sid and await login_btn.count() == 0:
                        result["status"] = "ok"
                        # Username try karo
                        try:
                            # Profile link from nav
                            prof = page.locator('a[href*="/"][aria-label]').nth(0)
                            href = await prof.get_attribute("href")
                            if href and href.startswith("/") and len(href) > 1:
                                result["username"] = href.strip("/").split("/")[0]
                        except Exception:
                            pass
                    else:
                        result["status"] = "invalid"
            except Exception as e:
                log.warning("check err: %s", e)
                result["status"] = "invalid"
            finally:
                await ctx.close()
                shutil.rmtree(udd, ignore_errors=True)
    except Exception as le:
        log.error("check launch fail: %s", le)
        result["status"] = "launch_fail"
    return result

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    with _state_lock:
        state = dict(_state)
    sid_results = request.args.get("sid_results", None)
    return render_template_string(HTML,
        state=state, messages=_messages, form=_form,
        error=request.args.get("error", ""),
        sid_results=[]
    )

@app.route("/check", methods=["POST"])
def check_sessions():
    raw  = request.form.get("sids", "").strip()
    sids = [s.strip() for s in raw.split(",") if s.strip()]
    if not sids:
        return redirect(url_for("index", error="Koi SID nahi diya."))

    results = []
    for sid in sids:
        r = asyncio.run(_quick_session_check(sid))
        results.append(r)

    with _state_lock:
        state = dict(_state)

    return render_template_string(HTML,
        state=state, messages=_messages, form=_form,
        error="", sid_results=results
    )

@app.route("/start", methods=["POST"])
def start():
    raw      = request.form.get("sids", "").strip()
    url      = request.form.get("url", "").strip()
    opponent = request.form.get("opponent", "").strip() or DEFAULT_OPPONENT
    n        = min(int(request.form.get("engine_count") or 2), 4)
    delay    = float(request.form.get("delay") or 0.3)
    lock     = bool(request.form.get("lock_enabled"))
    sids     = [s.strip() for s in raw.split(",") if s.strip()]
    gc_name  = DEFAULT_GC.replace("{opponent}", opponent)

    _form.update({
        "sids": raw, "url": url, "opponent": opponent,
        "engine_count": str(n), "delay": str(delay), "lock_enabled": lock,
    })

    if not sids: return redirect(url_for("index", error="Session ID chahiye."))
    if not url:  return redirect(url_for("index", error="Group URL chahiye."))

    err = start_strike(sids, url, gc_name, opponent, n, delay)
    if err: return redirect(url_for("index", error=err))
    return redirect(url_for("index"))

@app.route("/stop", methods=["POST"])
def stop():
    stop_strike()
    return redirect(url_for("index"))

@app.route("/msg/add", methods=["POST"])
def msg_add():
    t = request.form.get("text", "").strip()
    if t: _messages.append(t)
    return redirect(url_for("index"))

@app.route("/msg/del", methods=["POST"])
def msg_del():
    try:
        i = int(request.form.get("idx", -1))
        if 0 <= i < len(_messages): _messages.pop(i)
    except: pass
    return redirect(url_for("index"))

@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify(dict(_state))

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("DEVA💗WINE · Railway Edition · port %d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
