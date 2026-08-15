# -*- coding: utf-8 -*-
"""投稿の承認ページ（STEP4）
前日の夜に生成された翌日分の朝・夕2本を表示し、承認した投稿だけが自動投稿される。
合言葉でログイン（クッキー90日）。127.0.0.1:8894 で待ち、nginxがHTTPSで公開する。
"""
import hashlib
import hmac
import html
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))
DRAFTS_DIR = BASE / "drafts"
CLICKS = BASE / "clicks.jsonl"
NOTE_URL = "https://note.com/jolly_azalea745?utm_source=threads&utm_medium=profile"
PORT = 8894


def evening_hour(d):
    """投稿時刻の実験計画（第2期：2026-08-18から夜21時）。poster側と同じ表を持つ。"""
    return 21 if d >= date(2026, 8, 18) else 17


def slot_label(slot, date_str):
    if slot == "morning":
        return "朝 7:30"
    try:
        h = evening_hour(date.fromisoformat(date_str))
    except ValueError:
        h = 17
    return "夕 17:30" if h == 17 else f"夜 {h}:00"


def slot_time_passed(slot, date_str):
    """その投稿の予定時刻がすでに過ぎているか。"""
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return False
    now = datetime.now()
    if d < now.date():
        return True
    if d > now.date():
        return False
    if slot == "morning":
        return (now.hour, now.minute) >= (7, 30)
    h = evening_hour(d)
    return (now.hour, now.minute) >= ((h, 30) if h == 17 else (h, 0))
STATUS_LABEL = {
    "draft": ("未確認", "#b45309", "#fef3c7"),
    "approved": ("承認済み（自動投稿されます）", "#166534", "#dcfce7"),
    "rejected": ("却下（投稿されません）", "#991b1b", "#fee2e2"),
    "posted": ("投稿済み", "#1e40af", "#dbeafe"),
    "test_posted": ("テスト投稿済み（実際には出ていません）", "#3730a3", "#e0e7ff"),
    "error": ("投稿エラー（ログ確認）", "#991b1b", "#fee2e2"),
}


def env():
    conf = {}
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def token(conf):
    return hmac.new(conf.get("SECRET", "no-secret").encode(), b"threads-ok", hashlib.sha256).hexdigest()


def page(body, test_mode):
    mode = ("<div style='background:#fef3c7;color:#92400e;padding:8px 12px;border-radius:8px;margin-bottom:12px'>"
            "🧪 テストモード：承認しても実際のThreadsには投稿されません（記録のみ）</div>") if test_mode else ""
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Threads投稿の承認</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:sans-serif;margin:0;padding:16px;background:#f5f5f4;color:#1c1917}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
textarea{{width:100%;min-height:180px;font-size:15px;line-height:1.7;padding:10px;border:1px solid #d6d3d1;border-radius:8px}}
input[type=text]{{width:100%;font-size:14px;padding:8px;border:1px solid #d6d3d1;border-radius:8px}}
button{{font-size:15px;padding:10px 18px;border:none;border-radius:8px;cursor:pointer;margin-right:8px;margin-top:8px}}
.ok{{background:#16a34a;color:#fff}}.ng{{background:#dc2626;color:#fff}}.save{{background:#e7e5e4}}
.badge{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:13px}}
h1{{font-size:20px}} h2{{font-size:16px;margin:4px 0}}
.meta{{color:#78716c;font-size:13px}}
.tpv{{width:375px;max-width:100%;border:1px solid #e7e5e4;border-radius:12px;padding:12px 0;margin-top:6px;background:#fff}}
.tpv .tuser{{font-weight:700;font-size:15px;padding:0 15px 6px}}
.tpv .tbody{{font-size:15px;line-height:1.6;word-break:break-all;overflow-wrap:break-word;padding:0 15px}}
.tpv .tbody div{{min-height:1.6em}}
.tpv .warn{{background:#fee2e2;border-left:3px solid #dc2626}}
.warnnote{{font-size:13px;margin-top:4px}}
</style></head><body><h1>Threads投稿の承認</h1>
<div style="margin-bottom:12px"><a href="/report" style="color:#1d4ed8;font-size:14px">📊 分析レポートを見る →</a></div>
{mode}{body}
<script>
function cw(ch){{return /[\\u0020-\\u00FF\\uFF61-\\uFF9F]/.test(ch)?0.5:1;}}
function lastLine(par){{let cur=0;for(const c of par){{const w=cw(c);cur=(cur+w>24)?w:cur+w;}}return cur;}}
function total(par){{let t=0;for(const c of par)t+=cw(c);return t;}}
function renderPv(card){{
 const tas=card.querySelectorAll('textarea');
 const pvs=card.querySelectorAll('.tbody');
 let bad=0;
 [0,1].forEach(i=>{{
  if(!tas[i]||!pvs[i])return;
  pvs[i].innerHTML='';
  tas[i].value.split('\\n').forEach(par=>{{
   const d=document.createElement('div');
   d.textContent=par;
   if(par.trim()&&total(par)>24&&lastLine(par)<8){{d.className='warn';bad++;}}
   pvs[i].appendChild(d);
  }});
 }});
 const note=card.querySelector('.warnnote');
 if(note){{
  note.textContent=bad?'⚠️ 赤い段落はスマホ表示で最終行が8文字未満になります（'+bad+'か所）。文末を少し伸ばすか削ると直ります':'✓ 見た目OK（全段落の最終行が8文字以上）';
  note.style.color=bad?'#b91c1c':'#166534';
 }}
}}
async function decide(d,s,a){{
 const card=document.getElementById(d+'-'+s);
 const ta=card.querySelectorAll('textarea');
 const body={{date:d,slot:s,action:a,main:ta[0].value,reply:ta[1].value}};
 const r=await fetch('/api/decide',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
 if(r.ok){{location.reload();}}else{{alert('保存に失敗しました');}}
}}
async function postNow(d,s){{
 if(!confirm('今すぐThreadsに投稿します。よろしいですか？'))return;
 const btns=document.querySelectorAll('#'+CSS.escape(d+'-'+s)+' button');
 btns.forEach(b=>b.disabled=true);
 const r=await fetch('/api/post_now',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{date:d,slot:s}})}});
 const j=await r.json().catch(()=>({{}}));
 if(r.ok&&j.status==='posted'){{alert('投稿しました');}}else{{alert('投稿できませんでした：'+(j.detail||'ログを確認してください'));}}
 location.reload();
}}
function fitPv(){{
 document.querySelectorAll('.tpv .tbody').forEach(b=>{{
  const inner=b.clientWidth-31;
  if(inner>0)b.style.fontSize=(inner/24)+'px';
 }});
}}
document.querySelectorAll('.card').forEach(c=>{{
 renderPv(c);
 c.querySelectorAll('textarea').forEach(t=>t.addEventListener('input',()=>renderPv(c)));
}});
fitPv();
window.addEventListener('resize',fitPv);
</script></body></html>"""


def render_drafts(test_mode):
    today = date.today()
    cards = []
    for d in (today, today + timedelta(days=1)):
        f = DRAFTS_DIR / f"{d.isoformat()}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        cards.append(f"<h2 style='margin-top:20px'>{d.strftime('%m月%d日')} の投稿</h2>")
        for p in data["posts"]:
            label, fg, bg = STATUS_LABEL.get(p["status"], STATUS_LABEL["draft"])
            editable = p["status"] in ("draft", "approved", "rejected")
            dis = "" if editable else "disabled"
            btns = (f"<button class='ok' onclick=\"decide('{data['date']}','{p['slot']}','approve')\">承認する</button>"
                    f"<button class='ng' onclick=\"decide('{data['date']}','{p['slot']}','reject')\">却下する</button>"
                    f"<button class='save' onclick=\"decide('{data['date']}','{p['slot']}','save')\">修正だけ保存</button>") if editable else ""
            if p["status"] == "approved" and data["date"] == date.today().isoformat() and slot_time_passed(p["slot"], data["date"]):
                btns += (f"<button class='save' style='border:2px solid #1d4ed8;color:#1d4ed8;background:#eff6ff' "
                         f"onclick=\"postNow('{data['date']}','{p['slot']}')\">⚡ 今すぐ投稿する</button>"
                         "<div class='meta' style='margin-top:4px'>予定時刻を過ぎているため自動では投稿されません。このボタンでその場で投稿できます</div>")
            cards.append(f"""<div class="card" id="{data['date']}-{p['slot']}">
<h2>{slot_label(p['slot'], data['date'])} <span class="badge" style="color:{fg};background:{bg}">{label}</span></h2>
<div class="meta">元記事：{html.escape(p['article_title'])}</div>
<div class="meta">1枚目（本文）：</div>
<textarea {dis}>{html.escape(p['main'])}</textarea>
<div class="meta" style="margin-top:8px">2枚目（返信に続く文章）：</div>
<textarea {dis} style="min-height:140px">{html.escape(p['reply'])}</textarea>
<div class="meta" style="margin-top:10px">Threadsでの見え方（スマホと同じ幅・自動更新）：</div>
<div class="tpv"><div class="tuser">ribon.kenchiku.shukatsu2</div><div class="tbody"></div>
<div class="tuser" style="border-top:1px solid #f5f5f4;padding-top:8px;margin-top:8px">↳ 返信（2枚目）</div><div class="tbody"></div></div>
<div class="warnnote"></div>
{btns}</div>""")
    if not cards:
        cards.append("<p>表示できる投稿案がまだありません（毎晩21時に翌日分が作られます）。</p>")
    return page("".join(cards), test_mode)


LOGIN_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>合言葉</title>
<style>body{font-family:sans-serif;padding:40px 16px;background:#f5f5f4}
input,button{font-size:16px;padding:10px;border-radius:8px;border:1px solid #d6d3d1}
button{background:#1c1917;color:#fff;border:none;padding:10px 20px}</style></head>
<body><h1>合言葉を入力してください</h1>
<form method="POST" action="/login"><input type="password" name="aikotoba" autofocus>
<button type="submit">入る</button></form>{msg}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _conf(self):
        return env()

    def _authed(self, conf):
        cookie = self.headers.get("Cookie", "")
        return f"t_auth={token(conf)}" in cookie

    def _send(self, code, body, headers=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        conf = self._conf()
        if self.path.startswith("/go"):
            # noteへの計測リンク（認証不要）。クリックを記録して転送する
            try:
                with CLICKS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": datetime.now().isoformat(),
                                        "ua": self.headers.get("User-Agent", "")[:120]}) + "\n")
            except Exception:
                pass
            self.send_response(302)
            self.send_header("Location", NOTE_URL)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path.startswith("/callback"):
            self._handle_callback(conf)
            return
        if self.path.startswith("/login") or not self._authed(conf):
            self._send(200, LOGIN_PAGE.replace("{msg}", ""))
            return
        if self.path.startswith("/report"):
            rp = BASE / "report.html"
            if rp.exists():
                self._send(200, rp.read_text(encoding="utf-8"))
            else:
                self._send(200, "<p>レポートはまだありません（毎週月曜8:00に作成されます）。</p>")
            return
        self._send(200, render_drafts(conf.get("TEST_MODE", "1") == "1"))

    def _handle_callback(self, conf):
        """Threads認証の戻り先。コードを長期トークンに交換してtoken.jsonに保存する。"""
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [""])[0]
        if not code:
            self._send(400, "<p>コードがありません。もう一度お試しください。</p>")
            return
        app_id = conf.get("THREADS_APP_ID", "")
        secret = conf.get("THREADS_APP_SECRET", "")
        if not app_id or not secret:
            self._send(500, "<p>サーバー側の設定（アプリID・secret）が未登録です。</p>")
            return
        try:
            data = urllib.parse.urlencode({
                "client_id": app_id, "client_secret": secret,
                "grant_type": "authorization_code",
                "redirect_uri": "https://threads.210-131-223-173.sslip.io/callback",
                "code": code,
            }).encode()
            with urllib.request.urlopen(urllib.request.Request(
                    "https://graph.threads.net/oauth/access_token", data=data), timeout=60) as r:
                short = json.loads(r.read().decode())
            url = ("https://graph.threads.net/access_token?grant_type=th_exchange_token"
                   f"&client_secret={secret}&access_token={short['access_token']}")
            with urllib.request.urlopen(url, timeout=60) as r:
                long_ = json.loads(r.read().decode())
            (BASE / "token.json").write_text(json.dumps({
                "access_token": long_["access_token"],
                "refreshed_at": datetime.now().isoformat(),
                "user_id": short.get("user_id", ""),
            }), encoding="utf-8")
            self._send(200, "<h1>✅ Threads接続が完了しました</h1><p>この画面は閉じて構いません。</p>")
        except Exception as e:
            self._send(500, f"<h1>接続に失敗しました</h1><p>{html.escape(str(e)[:300])}</p>")

    def do_POST(self):
        conf = self._conf()
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        if self.path == "/login":
            given = parse_qs(raw).get("aikotoba", [""])[0]
            valid = [a.strip() for a in conf.get("AIKOTOBA", "").split(",") if a.strip()]
            if given and any(hmac.compare_digest(given, a) for a in valid):
                self._send(200, "<meta http-equiv='refresh' content='0;url=/'>",
                           {"Set-Cookie": f"t_auth={token(conf)}; Max-Age=7776000; Path=/; HttpOnly; Secure; SameSite=Lax"})
            else:
                self._send(200, LOGIN_PAGE.replace("{msg}", "<p style='color:#b91c1c'>合言葉が違います</p>"))
            return
        if self.path == "/api/post_now":
            if not self._authed(conf):
                self._send(403, "forbidden")
                return
            req = json.loads(raw)
            if req.get("date") != date.today().isoformat() or req.get("slot") not in ("morning", "evening"):
                self._send(400, json.dumps({"detail": "今日の分のみ投稿できます"}), {"Content-Type": "application/json"})
                return
            try:
                subprocess.run(["python3", str(BASE / "threads_poster.py"), req["slot"], "--force"],
                               cwd=BASE, timeout=180, capture_output=True)
            except subprocess.TimeoutExpired:
                self._send(500, json.dumps({"detail": "時間切れ"}), {"Content-Type": "application/json"})
                return
            f = DRAFTS_DIR / f"{req['date']}.json"
            status = ""
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                status = next((p["status"] for p in data["posts"] if p["slot"] == req["slot"]), "")
            body_out = json.dumps({"status": status, "detail": "" if status == "posted" else "投稿ログを確認してください"})
            self._send(200 if status == "posted" else 500, body_out, {"Content-Type": "application/json"})
            return
        if self.path == "/api/decide":
            if not self._authed(conf):
                self._send(403, "forbidden")
                return
            req = json.loads(raw)
            f = DRAFTS_DIR / f"{req['date']}.json"
            if not f.exists() or "/" in req["date"] or ".." in req["date"]:
                self._send(404, "not found")
                return
            data = json.loads(f.read_text(encoding="utf-8"))
            for p in data["posts"]:
                if p["slot"] == req["slot"] and p["status"] in ("draft", "approved", "rejected"):
                    p["main"] = str(req.get("main", p["main"]))[:480]
                    p["reply"] = str(req.get("reply", p["reply"]))[:480]
                    if req["action"] == "approve":
                        p["status"] = "approved"
                    elif req["action"] == "reject":
                        p["status"] = "rejected"
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._send(200, "ok")
            return
        self._send(404, "not found")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
