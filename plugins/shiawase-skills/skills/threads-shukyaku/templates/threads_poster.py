# -*- coding: utf-8 -*-
"""承認済み投稿をThreadsへ自動投稿する（STEP5）
cronで朝7:30（morning）・夕17:30（evening）に実行。承認された投稿だけを出す。
安全装置：1日4件上限・同一文の再投稿禁止・エラー時は再投稿せずログのみ・テストモード。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))
DRAFTS_DIR = BASE / "drafts"
HISTORY = BASE / "post_history.json"
TOKEN_FILE = BASE / "token.json"
LOG = BASE / "poster.log"
API = "https://graph.threads.net/v1.0"
DAILY_LIMIT = 4  # 本文2＋返信2


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def env():
    conf = {}
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def evening_hour(d):
    """投稿時刻の実験計画（第2期：2026-08-18から夜21時）。approval_app側と同じ表を持つ。"""
    return 21 if d >= date(2026, 8, 18) else 17


def notify(conf, title, message, tag="loudspeaker"):
    """携帯へのプッシュ通知（ntfy）。失敗しても本体の動きは止めない。"""
    topics = [t.strip() for t in conf.get("NTFY_TOPIC", "").split(",") if t.strip()]
    for topic in topics:
        try:
            body = json.dumps({
                "topic": topic, "title": title, "message": message,
                "click": "https://threads.210-131-223-173.sslip.io/", "tags": [tag],
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request("https://ntfy.sh", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            log(f"通知失敗（無視して続行）: {e}")


def http_post(url, params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
        return json.loads(r.read().decode())


def http_get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())


def get_token(conf):
    """長期トークンを読み、7日ごとに更新する（60日期限対策）。"""
    if TOKEN_FILE.exists():
        t = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    else:
        t = {"access_token": conf.get("THREADS_ACCESS_TOKEN", ""), "refreshed_at": "2000-01-01"}
    if not t["access_token"]:
        return None
    age_days = (datetime.now() - datetime.fromisoformat(t["refreshed_at"])).days
    if age_days >= 7:
        try:
            res = http_get(f"{API.replace('/v1.0','')}/refresh_access_token?grant_type=th_refresh_token&access_token={t['access_token']}")
            t = {"access_token": res["access_token"], "refreshed_at": datetime.now().isoformat()}
            log("トークンを更新しました")
        except Exception as e:
            log(f"⚠️ トークン更新失敗（既存トークンで続行）: {e}")
    TOKEN_FILE.write_text(json.dumps(t), encoding="utf-8")
    return t["access_token"]


def publish_text(token_, text, reply_to=None):
    params = {"media_type": "TEXT", "text": text, "access_token": token_}
    if reply_to:
        params["reply_to_id"] = reply_to
    creation = http_post(f"{API}/me/threads", params)
    time.sleep(3)
    result = http_post(f"{API}/me/threads_publish", {"creation_id": creation["id"], "access_token": token_})
    post_id = result["id"]
    permalink = ""
    try:
        permalink = http_get(f"{API}/{post_id}?fields=permalink&access_token={token_}").get("permalink", "")
    except Exception:
        pass
    return post_id, permalink


def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "morning"
    conf = env()
    test_mode = conf.get("TEST_MODE", "1") == "1"
    if slot == "evening" and "--force" not in sys.argv:
        expected = evening_hour(date.today())
        if datetime.now().hour != expected:
            log(f"[evening] 実験計画の時刻（{expected}時台）ではないため何もしません")
            return
    today = date.today().isoformat()
    f = DRAFTS_DIR / f"{today}.json"
    if not f.exists():
        log(f"[{slot}] 下書きファイルなし（{today}）")
        return
    data = json.loads(f.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []

    post = next((p for p in data["posts"] if p["slot"] == slot), None)
    if not post:
        log(f"[{slot}] 該当スロットなし")
        return
    slot_jp = "朝" if slot == "morning" else "夕方"
    if post["status"] != "approved":
        log(f"[{slot}] 状態が {post['status']} のため投稿しません（承認済みのみ投稿）")
        if post["status"] == "draft":
            notify(conf, f"【リボン】{slot_jp}の投稿は出ませんでした",
                   "承認されていなかったため投稿していません。次回分はページで承認してください。", "warning")
        return

    # 安全装置
    today_count = sum(1 for h in history if h.get("date") == today and h.get("status") == "posted")
    if today_count >= DAILY_LIMIT:
        log(f"[{slot}] ⛔ 1日の投稿上限（{DAILY_LIMIT}）に達しているため中止")
        return
    if any(h.get("main") == post["main"] for h in history):
        log(f"[{slot}] ⛔ 同一本文が過去に投稿済みのため中止")
        return

    if test_mode:
        post["status"] = "test_posted"
        history.append({"date": today, "slot": slot, "article_no": post["article_no"],
                        "hen": post.get("hen", ""), "hen_no": post.get("hen_no", 0),
                        "main": post["main"], "reply": post["reply"], "status": "test_posted",
                        "posted_at": datetime.now().isoformat()})
        log(f"[{slot}] 🧪 テストモード：実投稿せず記録のみ")
    else:
        token_ = get_token(conf)
        if not token_:
            log(f"[{slot}] ⛔ Threadsトークン未設定のため投稿できません")
            return
        try:
            post_id, permalink = publish_text(token_, post["main"])
            reply_id = ""
            if post.get("reply"):
                time.sleep(5)
                reply_id, _ = publish_text(token_, post["reply"], reply_to=post_id)
            post["status"] = "posted"
            history.append({"date": today, "slot": slot, "article_no": post["article_no"],
                            "hen": post.get("hen", ""), "hen_no": post.get("hen_no", 0),
                            "main": post["main"], "reply": post["reply"], "status": "posted",
                            "threads_post_id": post_id, "threads_url": permalink,
                            "reply_post_id": reply_id, "posted_at": datetime.now().isoformat()})
            log(f"[{slot}] ✅ 投稿完了 {permalink}")
            notify(conf, f"【リボン】{slot_jp}の投稿が完了しました", "1枚目と2枚目（返信）を投稿しました。", "white_check_mark")
            notify(conf, f"{slot_jp}の投稿が完了しました", post["main"][:80] + "…", "white_check_mark")
        except Exception as e:
            post["status"] = "error"
            history.append({"date": today, "slot": slot, "article_no": post["article_no"],
                            "main": post["main"], "status": "error", "error": str(e)[:300],
                            "posted_at": datetime.now().isoformat()})
            log(f"[{slot}] ❌ 投稿エラー（再投稿はしません）: {e}")
            notify(conf, f"【リボン】{slot_jp}の投稿でエラーが起きました", "自動の再投稿はしません。ログを確認してください。", "x")

    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
