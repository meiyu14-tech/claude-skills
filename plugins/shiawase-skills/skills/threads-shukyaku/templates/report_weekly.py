# -*- coding: utf-8 -*-
"""週次レポート生成（毎週月曜8:00にcronで実行）
投稿履歴の反応データ・noteリンクのクリック記録・フォロワー数を集計し、
report.html を作って携帯に通知する。承認ページの /report で表示される。
"""
import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))
HISTORY = BASE / "post_history.json"
CLICKS = BASE / "clicks.jsonl"
FOLLOWERS = BASE / "followers_history.json"
TOKEN_FILE = BASE / "token.json"
OUT = BASE / "report.html"
API = "https://graph.threads.net/v1.0"
MODEL = "gemini-flash-latest"


def env():
    conf = {}
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def fetch_followers():
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["access_token"]
        url = f"{API}/me/threads_insights?metric=followers_count&access_token={token}"
        data = json.loads(urllib.request.urlopen(url, timeout=60).read().decode())
        return data["data"][0]["total_value"]["value"]
    except Exception:
        return None


def load_week(history, start, end):
    return [h for h in history if h.get("status") == "posted" and start <= h.get("date", "") <= end]


def agg(posts):
    views = sum(h.get("insights", {}).get("views", 0) for h in posts)
    likes = sum(h.get("insights", {}).get("likes", 0) for h in posts)
    return views, likes


def pct(now, prev):
    if not prev:
        return ""
    d = round((now - prev) / prev * 100)
    return f"先週比 {'+' if d >= 0 else ''}{d}%"


def gemini_learn(key, summary):
    prompt = f"""以下はThreads自動投稿（建築学生向け就活ノウハウ発信）の今週の実測データです。
{summary}
このデータから読み取れる傾向と、次の投稿への提案を、日本語で3文以内・断定しすぎない書き方でまとめてください。データにない事実は書かないこと。出力は本文のみ。"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4}}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"（自動分析は今週作成できませんでした：{str(e)[:80]}）"


NOTE_LIKES = BASE / "note_likes_history.json"
NOTE_VIEWS = BASE / "note_views_manual.json"


def fetch_note_likes(creator):
    """noteの公開APIから全記事のスキ数を取得（ビュー数は非公開のため取得不可）。"""
    items = {}
    titles = {}
    for page in range(1, 6):
        url = f"https://note.com/api/v2/creators/{creator}/contents?kind=note&page={page}"
        try:
            data = json.loads(urllib.request.urlopen(url, timeout=60).read().decode())
        except Exception:
            break
        c = data.get("data", {})
        for n in c.get("contents", []):
            items[n.get("key", "")] = n.get("likeCount", 0)
            titles[n.get("key", "")] = n.get("name", "")[:30]
        if c.get("isLastPage"):
            break
    return items, titles


def note_section(conf):
    creator = conf.get("NOTE_CREATOR", "")
    if not creator:
        return ""
    items, titles = fetch_note_likes(creator)
    hist = json.loads(NOTE_LIKES.read_text(encoding="utf-8")) if NOTE_LIKES.exists() else []
    prev = hist[-1]["items"] if hist else {}
    hist.append({"date": date.today().isoformat(), "items": items})
    NOTE_LIKES.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    total = sum(items.values())
    delta = total - sum(prev.values()) if prev else 0
    rows = "".join(
        f"<tr><td>{titles.get(k,'')}</td><td class='num'>{v}</td>"
        f"<td class='num'>{'+' + str(v - prev.get(k, 0)) if prev and v - prev.get(k, 0) > 0 else '—'}</td></tr>"
        for k, v in sorted(items.items(), key=lambda kv: -kv[1])) or "<tr><td colspan='3'>記事なし</td></tr>"

    manual = json.loads(NOTE_VIEWS.read_text(encoding="utf-8")) if NOTE_VIEWS.exists() else []
    mv_rows = "".join(f"<tr><td>{m['date']}</td><td class='num'>{m['views']:,}</td></tr>" for m in manual[-5:]) \
        or "<tr><td colspan='2'>まだ入力がありません</td></tr>"

    return f"""<div class="card"><h2>note側の反応（スキ数・自動取得）</h2>
<table><tr><th>記事</th><th class="num" style="width:16%">スキ</th><th class="num" style="width:16%">今週</th></tr>{rows}</table>
<div class="sub" style="margin-top:6px">合計スキ {total}（前回比 {'+' if delta >= 0 else ''}{delta}）</div></div>
<div class="card"><h2>noteのビュー数（手入力・週1回）</h2>
<div class="sub">ビュー数はnoteが外部公開していないため、<a href="https://note.com/sitesettings/stats">noteのアクセス状況画面</a>の「全体ビュー」を見て入力してください</div>
<table><tr><th>入力日</th><th class="num">全体ビュー</th></tr>{mv_rows}</table>
<div style="margin-top:8px"><input id="nv" type="number" placeholder="今週の全体ビュー" style="font-size:15px;padding:8px;border:1px solid #d6d3d1;border-radius:8px;width:60%">
<button onclick="saveNv()" style="font-size:15px;padding:8px 14px;border:none;border-radius:8px;background:#1c1917;color:#fff">保存</button></div>
<script>async function saveNv(){{const v=document.getElementById('nv').value;if(!v)return;
const r=await fetch('/api/note_views',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{views:parseInt(v)}})}});
alert(r.ok?'保存しました（次回のレポート生成から表に載ります）':'保存できませんでした');}}</script></div>"""


def notify(conf, title, message):
    for topic in [t.strip() for t in conf.get("NTFY_TOPIC", "").split(",") if t.strip()]:
        try:
            body = json.dumps({"topic": topic, "title": title, "message": message,
                               "click": "https://threads.210-131-223-173.sslip.io/report",
                               "tags": ["bar_chart"]}, ensure_ascii=False).encode()
            urllib.request.urlopen(urllib.request.Request("https://ntfy.sh", data=body,
                                   headers={"Content-Type": "application/json"}), timeout=15)
        except Exception:
            pass


def main():
    conf = env()
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    today = date.today()
    week_end = today - timedelta(days=1)          # 昨日（日曜）まで
    week_start = week_end - timedelta(days=6)      # 月曜
    prev_end = week_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)

    posts = load_week(history, week_start.isoformat(), week_end.isoformat())
    prev_posts = load_week(history, prev_start.isoformat(), prev_end.isoformat())
    views, likes = agg(posts)
    p_views, p_likes = agg(prev_posts)

    # クリック集計
    clicks, p_clicks = [], 0
    hour_buckets = defaultdict(int)
    if CLICKS.exists():
        for line in CLICKS.read_text(encoding="utf-8").splitlines():
            try:
                t = datetime.fromisoformat(json.loads(line)["t"])
            except Exception:
                continue
            d = t.date()
            if week_start <= d <= week_end:
                clicks.append(t)
                hour_buckets["朝（6-10時）" if 6 <= t.hour <= 10 else "昼（11-16時）" if 11 <= t.hour <= 16 else "夜・深夜（17-5時）"] += 1
            elif prev_start <= d <= prev_end:
                p_clicks += 1
    click_rate = f"{len(clicks) / views * 100:.1f}%" if views else "—"

    # フォロワー
    followers = fetch_followers()
    fh = json.loads(FOLLOWERS.read_text(encoding="utf-8")) if FOLLOWERS.exists() else []
    f_delta = ""
    if followers is not None:
        if fh:
            f_delta = f"今週 {'+' if followers - fh[-1]['count'] >= 0 else ''}{followers - fh[-1]['count']}人"
        fh.append({"date": today.isoformat(), "count": followers})
        FOLLOWERS.write_text(json.dumps(fh, ensure_ascii=False), encoding="utf-8")

    # ベスト3・編別・時刻別
    ranked = sorted(posts, key=lambda h: h.get("insights", {}).get("views", 0), reverse=True)[:3]
    hen_stats = defaultdict(list)
    hour_stats = defaultdict(list)
    for h in posts:
        v = h.get("insights", {}).get("views", 0)
        hen_stats[h.get("hen", "不明")].append(v)
        try:
            hr = datetime.fromisoformat(h["posted_at"]).hour
            hour_stats[f"{hr}時台"].append(v)
        except Exception:
            pass

    def rows_hen():
        items = sorted(hen_stats.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
        return "".join(f"<tr><td>{k}</td><td class='num'>{sum(v)//len(v):,}</td><td class='num'>{len(v)}本</td></tr>" for k, v in items)

    def rows_hour():
        items = sorted(hour_stats.items())
        return "".join(f"<tr><td>{k}</td><td class='num'>{sum(v)//len(v):,}</td><td class='num'>{len(v)}本</td></tr>" for k, v in items)

    def rows_rank():
        out = []
        for i, h in enumerate(ranked, 1):
            title = h.get("main", "").splitlines()[0][:40]
            ins = h.get("insights", {})
            out.append(f"<tr><td class='rank'>{i}位</td><td>{title}</td><td class='num'>{ins.get('views',0):,}</td><td class='num'>{ins.get('likes',0)}</td></tr>")
        return "".join(out)

    def rows_all():
        """全投稿の明細（合計閲覧数の内訳）。日付順。"""
        out = []
        slot_jp = {"morning": "朝", "evening": "夕"}
        for h in sorted(posts, key=lambda x: (x.get("date", ""), x.get("slot", ""))):
            ins = h.get("insights", {})
            title = h.get("main", "").splitlines()[0][:30]
            link = f"<a href=\"{h.get('threads_url','')}\">開く</a>" if h.get("threads_url") else ""
            out.append(f"<tr><td>{h.get('date','')[5:]} {slot_jp.get(h.get('slot'),'')}</td><td>{title}</td>"
                       f"<td class='num'>{ins.get('views',0):,}</td><td class='num'>{ins.get('likes',0)}</td>"
                       f"<td class='num'>{ins.get('replies',0)}</td><td class='num'>{ins.get('reposts',0) + ins.get('quotes',0)}</td><td>{link}</td></tr>")
        return "".join(out) or "<tr><td colspan='7'>投稿なし</td></tr>"

    def rows_click():
        return "".join(f"<tr><td>{k}</td><td class='num'>{v}</td></tr>" for k, v in hour_buckets.items()) or "<tr><td colspan='2'>まだクリックがありません</td></tr>"

    summary = (f"期間{week_start}〜{week_end}／投稿{len(posts)}本／合計閲覧{views}（先週{p_views}）／"
               f"合計いいね{likes}（先週{p_likes}）／noteリンククリック{len(clicks)}（先週{p_clicks}）／"
               f"編別平均閲覧{dict((k, sum(v)//len(v)) for k, v in hen_stats.items())}／"
               f"投稿時刻別平均閲覧{dict((k, sum(v)//len(v)) for k, v in hour_stats.items())}")
    learn = gemini_learn(conf.get("GEMINI_API_KEY", ""), summary)

    html_out = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Threads週次レポート</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:sans-serif;background:#f5f5f4;color:#1c1917;line-height:1.7;padding:16px}}
.wrap{{max-width:520px;margin:0 auto}}h1{{font-size:1.3em;margin:8px 0 2px}}
.sub{{color:#78716c;font-size:.85em;margin-bottom:14px}}
.card{{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card h2{{font-size:1em;margin-bottom:8px;border-left:5px solid #1c1917;padding-left:8px}}
.tiles{{display:flex;gap:8px;flex-wrap:wrap}}
.tile{{flex:1 1 40%;background:#fafaf9;border-radius:10px;padding:10px;text-align:center}}
.tile .n{{font-size:1.5em;font-weight:700}}.tile .l{{font-size:.75em;color:#78716c}}.tile .d{{font-size:.75em;color:#166534}}
table{{width:100%;table-layout:fixed;border-collapse:collapse;font-size:.85em}}
th,td{{padding:7px 6px;border-bottom:1px solid #f0efee;text-align:left;word-break:break-word}}
th{{color:#78716c;font-weight:normal}}.num{{text-align:right}}.rank{{font-weight:700;color:#b45309}}
.learn{{background:#eff6ff;border-radius:10px;padding:10px 12px;font-size:.9em}}</style></head><body><div class="wrap">
<h1>📊 Threads週次レポート</h1>
<div style="margin-bottom:10px"><a href="/" style="color:#1d4ed8;font-size:14px">← 投稿の承認ページへ戻る</a></div>
<div class="sub">{week_start.strftime('%Y年%m月%d日')}〜{week_end.strftime('%m月%d日')}｜作成 {datetime.now().strftime('%m/%d %H:%M')}</div>
<div class="card"><h2>今週のまとめ（Threads側）</h2><div class="tiles">
<div class="tile"><div class="n">{len(posts)}</div><div class="l">投稿数</div></div>
<div class="tile"><div class="n">{views:,}</div><div class="l">合計閲覧数</div><div class="d">{pct(views, p_views)}</div></div>
<div class="tile"><div class="n">{likes:,}</div><div class="l">合計いいね</div><div class="d">{pct(likes, p_likes)}</div></div>
<div class="tile"><div class="n">{followers if followers is not None else '—'}</div><div class="l">フォロワー</div><div class="d">{f_delta}</div></div>
<div class="tile" style="border:2px solid #1d4ed8"><div class="n">{len(clicks)}</div><div class="l">noteリンクのクリック</div><div class="d">{pct(len(clicks), p_clicks)}</div></div>
<div class="tile"><div class="n">{click_rate}</div><div class="l">閲覧→クリック率</div></div>
</div></div>
<div class="card"><h2>全投稿の明細（合計閲覧数の内訳）</h2>
<div style="overflow-x:auto"><table style="min-width:0">
<tr><th style="width:14%">投稿</th><th>題名</th><th class="num" style="width:13%">閲覧</th><th class="num" style="width:11%">いいね</th><th class="num" style="width:10%">返信</th><th class="num" style="width:12%">再共有</th><th style="width:9%"></th></tr>{rows_all()}</table></div></div>
<div class="card"><h2>よく読まれた投稿 ベスト3</h2><table>
<tr><th style="width:9%"></th><th>投稿（1行目）</th><th style="width:17%" class="num">閲覧</th><th style="width:14%" class="num">いいね</th></tr>{rows_rank()}</table></div>
<div class="card"><h2>編ごとの平均閲覧数</h2><table>
<tr><th>編</th><th class="num">平均閲覧</th><th class="num">投稿数</th></tr>{rows_hen()}</table></div>
<div class="card"><h2>投稿時刻ごとの平均閲覧数（時刻実験）</h2><table>
<tr><th>投稿時刻</th><th class="num">平均閲覧</th><th class="num">投稿数</th></tr>{rows_hour()}</table>
<div class="sub" style="margin-top:6px">計画：8/17まで夕17:30／8/18から夜21:00に切り替えて比較</div></div>
<div class="card"><h2>noteリンクがクリックされた時間帯</h2><table>
<tr><th>時間帯</th><th class="num">クリック数</th></tr>{rows_click()}</table></div>
{note_section(conf)}
<div class="card"><h2>今週の学び（自動分析）</h2><div class="learn">{learn}</div></div>
</div></body></html>"""
    OUT.write_text(html_out, encoding="utf-8")
    print(f"レポート作成: {OUT}")
    notify(conf, "【リボン】今週のThreadsレポートができました",
           f"投稿{len(posts)}本・閲覧{views:,}・noteクリック{len(clicks)}。タップで詳細が開きます。")


if __name__ == "__main__":
    main()
