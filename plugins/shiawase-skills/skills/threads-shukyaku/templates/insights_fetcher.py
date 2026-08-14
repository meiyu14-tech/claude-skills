# -*- coding: utf-8 -*-
"""投稿の反応データ取得（STEP8）
直近14日の投稿について、閲覧数・いいね・返信・リポスト・引用をThreads APIから取得し、
投稿履歴（post_history.json）に書き足す。毎日20:50に実行（21:00の生成が最新データを使えるように）。
Threads未接続（トークンなし）の間は何もせず終わる。
"""
import json
import os
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))
HISTORY = BASE / "post_history.json"
TOKEN_FILE = BASE / "token.json"
LOG = BASE / "insights.log"
API = "https://graph.threads.net/v1.0"
METRICS = "views,likes,replies,reposts,quotes"


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_token():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("access_token", "")
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("THREADS_ACCESS_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def fetch_insights(token, media_id):
    url = f"{API}/{media_id}/insights?metric={METRICS}&access_token={token}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode())
    out = {}
    for item in data.get("data", []):
        values = item.get("values", [{}])
        out[item["name"]] = values[0].get("value", 0) if values else 0
    return out


def main():
    token = get_token()
    if not token:
        log("Threads未接続のため取得なし（正常）")
        return
    if not HISTORY.exists():
        log("投稿履歴なし")
        return
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    updated = 0
    for h in history:
        if h.get("status") != "posted" or not h.get("threads_post_id"):
            continue
        if h.get("date", "") < cutoff:
            continue
        try:
            h["insights"] = fetch_insights(token, h["threads_post_id"])
            h["insights_at"] = datetime.now().isoformat()
            updated += 1
        except Exception as e:
            log(f"⚠️ 取得失敗 {h.get('date')}/{h.get('slot')}: {str(e)[:150]}")
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"反応データ更新: {updated}件")


if __name__ == "__main__":
    main()
