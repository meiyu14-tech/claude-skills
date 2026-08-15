# -*- coding: utf-8 -*-
"""Threads投稿案の生成エンジン（STEP2）
記事台帳＋就活時期カレンダー＋投稿履歴からGeminiで朝・夕の投稿案を作る。
有料記事の「有料部分の概要」「投稿で明かさないこと」はGeminiに渡さない。
PCでもVPSでも動く：台帳は同じフォルダの ledger.md を優先し、無ければVaultの正本を読む。
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))
VAULT_LEDGER = Path(r"G:\マイドライブ\ObsidianVault\MyVault\幸せ貢献業\プロジェクト\進行中\Threads_note自動集客システム\Threads_note自動集客_記事台帳.md")
HISTORY = BASE / "post_history.json"
DRAFTS_DIR = BASE / "drafts"
MODEL = "gemini-flash-latest"

ALLOWED_FIELDS = [
    "テーマ", "解決する悩み", "対象となる学生", "有効な時期",
    "記事の重要ポイント", "Threads投稿の切り口", "noteへの誘導文脈",
    "投稿で明かしてよいこと（フック用）",
]
FORBIDDEN_FIELDS = ["有料部分の概要", "投稿で明かさないこと"]

SEASON = {
    1: "ポートフォリオ制作・組織設計の選考・面接準備の時期",
    2: "本選考面接・ポートフォリオ仕上げの時期",
    3: "広報解禁（3/1）・本選考面接・就活全体像の時期",
    4: "マイページ登録・サマリ作成開始・設計理念整理の時期",
    5: "夏インターン応募・ES・サマリ準備の時期",
    6: "夏インターン応募締切・インターン選考面接の時期",
    7: "インターン選考・参加準備の時期",
    8: "夏インターン参加中・ゼネコン早期選考の書類準備の時期",
    9: "夏インターン終盤・早期選考の一次面接が始まる時期",
    10: "早期選考面接・即日設計の練習開始（理想は10月）の時期",
    11: "本選考書類＋即日設計試験の時期",
    12: "即日設計・ポートフォリオ制作の時期",
}
SEASON_ARTICLES = {
    1: [7, 10, 17, 15, 13, 18], 2: [15, 17, 13, 10, 7, 24],
    3: [24, 26, 15, 17, 13, 25], 4: [12, 22, 14, 24, 23, 8],
    5: [12, 22, 16, 14, 23, 9], 6: [16, 6, 15, 17, 13, 9],
    7: [16, 6, 15, 17, 9, 3], 8: [16, 6, 24, 9, 3, 23, 25, 1],
    9: [16, 6, 15, 17, 24, 21], 10: [21, 18, 20, 19, 15, 17, 3],
    11: [21, 18, 20, 19, 11, 13], 12: [19, 21, 10, 11, 3, 7],
}
MORNING_TYPES = ["ノウハウ型", "問題提起型"]
EVENING_TYPES = ["経験談型", "問いかけ型"]

# 表記ルール（2026-08-15 伊藤さん指示）。生成後に必ず機械置換して保証する
REPLACEMENTS = [
    ("夏インターン", "夏季インターン"),
    ("OBOG", "OB・OG"),
    ("OB/OG", "OB・OG"),
    ("🎀", "🌸"),
    ("『", "「"),
    ("』", "」"),
]


def sanitize(text):
    for a, b in REPLACEMENTS:
        text = text.replace(a, b)
    return text

SERIES_TITLE = "地方大学でも戦える就活戦略"
# 記事No → 編名（1枚目の題名に使う）
HEN_MAP = {
    1: "地方大学編", 2: "自己紹介編", 3: "就活生活編", 4: "進路編",
    5: "コンペ編", 6: "インターン編", 7: "ポートフォリオ編", 8: "ES編",
    9: "お金編", 10: "ポートフォリオ編", 11: "即日設計編", 12: "ポートフォリオ編",
    13: "面接編", 14: "設計理念編", 15: "面接編", 16: "インターン編",
    17: "面接編", 18: "即日設計編", 19: "即日設計編", 20: "即日設計編",
    21: "即日設計編", 22: "ポートフォリオ編", 23: "情報収集編", 24: "スケジュール編",
    25: "地方大学編", 26: "自己紹介編",
}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"


def circled(n):
    return CIRCLED[n - 1] if 1 <= n <= len(CIRCLED) else f"({n})"


def hen_number(hen, history, used_in_run):
    """その編で何本目かを数える（投稿済み＋この実行内で既に割り当てた分＋1）。"""
    posted = sum(1 for h in history if h.get("hen") == hen and h.get("status") in ("posted", "test_posted"))
    return posted + used_in_run.get(hen, 0) + 1


def ledger_path():
    local = BASE / "ledger.md"
    if local.exists():
        return local
    if VAULT_LEDGER.exists():
        return VAULT_LEDGER
    raise SystemExit("NG: 記事台帳（ledger.md）が見つかりません")


def load_key():
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("\ufeff")
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("NG: .envにGEMINI_API_KEYがありません")


def parse_ledger():
    text = ledger_path().read_text(encoding="utf-8")
    articles = []
    for block in re.split(r"\n### ", text)[1:]:
        lines = block.splitlines()
        m = re.match(r"記事(\d+)：(.+)", lines[0])
        if not m:
            continue
        art = {"no": int(m.group(1)), "title": m.group(2).strip(), "fields": {}}
        current = None
        for ln in lines[1:]:
            fm = re.match(r"- ([^:：]+)[:：] ?(.*)", ln)
            if fm:
                name = fm.group(1).strip()
                if name == "URL":
                    art["url"] = fm.group(2).strip()
                    current = None
                elif name == "区分":
                    art["kubun"] = fm.group(2).strip()
                    current = None
                elif any(name.startswith(f) for f in FORBIDDEN_FIELDS):
                    current = None
                elif any(name.startswith(f) for f in ALLOWED_FIELDS):
                    current = name
                    art["fields"][current] = fm.group(2).strip()
                else:
                    current = None
            elif ln.startswith("  ") and current:
                art["fields"][current] += "\n" + ln.strip()
        articles.append(art)
    return {a["no"]: a for a in articles}


def load_history():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return []


def pick_articles(articles, history, target_date):
    recent_cutoff = (target_date - timedelta(days=14)).isoformat()
    recent = {h["article_no"] for h in history if h.get("date", "") >= recent_cutoff}
    order = SEASON_ARTICLES[target_date.month]
    candidates = [n for n in order if n in articles and n not in recent]
    if len(candidates) < 2:
        candidates += [n for n in articles if n not in candidates and n not in recent]
    if len(candidates) < 2:
        candidates = list(order)
    return candidates[0], candidates[1]


LINE_WIDTH = 24   # Threadsスマホ表示の折り返し幅（全角換算・実投稿で実測）
MIN_LAST_LINE = 8  # 折り返し後の最終行に必要な最低文字数（全角換算）


def char_width(c):
    return 1.0 if unicodedata.east_asian_width(c) in ("F", "W", "A") else 0.5


def last_line_width(par):
    """全角24文字幅で折り返した場合の最終行の幅を返す。"""
    cur = 0.0
    for c in par:
        w = char_width(c)
        cur = w if cur + w > LINE_WIDTH else cur + w
    return cur


def layout_problems(text):
    """折り返し最終行が8文字未満になる段落の一覧（(段落先頭, 最終行幅)）。"""
    probs = []
    for par in text.split("\n"):
        par = par.strip()
        if not par:
            continue
        total = sum(char_width(c) for c in par)
        if total > LINE_WIDTH and last_line_width(par) < MIN_LAST_LINE:
            probs.append((par[:14], last_line_width(par)))
    return probs


def top_posts_reference(history):
    """反応データがある投稿から閲覧数上位2本を選び、書き方の参考としてプロンプトに渡す（STEP9）。"""
    scored = [h for h in history if h.get("status") == "posted" and h.get("insights", {}).get("views")]
    if not scored:
        return ""
    scored.sort(key=lambda h: h["insights"]["views"], reverse=True)
    lines = []
    for h in scored[:2]:
        ins = h["insights"]
        lines.append(f"（閲覧{ins.get('views',0)}・いいね{ins.get('likes',0)}）\n{h['main']}")
    return ("\n# 反応が良かった過去投稿（書き方・雰囲気の参考。内容やテーマは真似せず、文体・構成の傾向だけ参考にする）\n"
            + "\n---\n".join(lines) + "\n")


def build_prompt(art, slot, target_date):
    role = ("朝の投稿：知識・気づき・準備を促す内容。型は" + "・".join(MORNING_TYPES)
            if slot == "morning" else
            "夕方の投稿：経験談・悩みへの共感・深掘り。型は" + "・".join(EVENING_TYPES))
    fields = "\n".join(f"{k}: {v}" for k, v in art["fields"].items())
    season = SEASON[target_date.month]
    return f"""あなたはnoteで建築学生向け就活ノウハウを発信している「リボン」本人としてThreads投稿を書きます。
著者背景：地方公立大学の修士学生・27卒・OBOGゼロの環境から準大手ゼネコンの意匠設計職に内定。受賞歴は卒業設計の1つのみ。

# 発信理念（絶対に守る）
- 自分が就活で困ったことを、これから就活する建築学生に先に教えてあげたい
- 不安を煽らない。誇張しない。営業っぽくしない。まず役に立つ
- noteに存在しない情報を作らない（下の記事情報の範囲だけで書く）
- 有料記事の場合「投稿で明かしてよいこと」の範囲を超える中身は書かない

# 今の時期
{target_date.strftime('%Y年%m月%d日')}。建築学生は「{season}」。

# 今回の役割
{role}

# 元にするnote記事の情報
タイトル: {art['title']}
区分: {art.get('kubun', '無料')}
{fields}

# 投稿の形（重要）
1枚目（main）と、その返信につなげる2枚目（reply）の**続きもの**として書く。
- 1枚目：全角320字以内。**題名は書かない**（システムが冒頭に自動で付けるため、いきなり本文から始める）。書き出しの1行で対象読者が「自分のことだ」と気づける具体性。悩み・状況を描き、**続きが気になるところで切る**（問いかけ・「？」・言いかけで終えるなど）
- **1枚目の最後は「言いかけ・余韻」で終える**：文を途中で止めて読点「、」（または「、、」）で切るか、含みのある一言を句点「。」で置いて次を匂わせる。**疑問符「？」で終える問いかけは使わない**（実際のアップ済み投稿はすべて読点や句点の言いかけで終えており、そちらが自然に次へつながるため。例：「一番大きな負担になったのは交通費ではなくて、」「別のところにありました、、！」）。「〜してくれました。」のような完全に完結した報告文で締めるのも禁止
- 2枚目：全角400字以内。**冒頭の1文は1枚目の最後の「引き」に直接答える形で書き始める**（一般論や別の話題から始めない）。答え・学び・励ましを書き、前向きに締める
- 時期の話題は、流れに自然に馴染む場合に限り1文まで。唐突に挿入しない
- 1〜2文ごとに改行して読みやすく。ハッシュタグは付けない。絵文字は2枚合計2個まで（🌸など柔らかいもの。🎀は使わない）
- 表記ルール：「夏季インターン」と書く（「夏インターン」は不可）。「OB・OG」と中黒入りで書く（「OBOG」は不可）
- **見た目のルール（重要）**：Threadsのスマホ画面は全角約24文字で自動折り返しされる。各段落（改行で区切られた一かたまり）は、24文字で折り返したときの**最終行が全角8文字以上**になるよう文の長さを調整する。「た、」「す」など1〜7文字だけが次の行にポツンと残る形は禁止。文末の調整（語尾を変える・語を足す/削る）で整える
- **URLは絶対に書かない**（noteはプロフィール欄から辿れるため）。「プロフィールのnoteに詳しくまとめています」という一言は、自然な流れのときだけ2枚目の最後に入れてよい（毎回は入れない）

# 文体見本（この人の実際の投稿。この空気感に合わせる）
1枚目：「【地方大学でも戦える就活戦略】普通すぎる建築学生だった私の就活記録／就活中は、コンペ賞歴20個以上という方を見て、「意匠設計職の就活は難しいのかな、、」と思うことが何度もありました。／その方たちが人一倍努力してきたことは分かってはいても、その実績や才能が羨ましく思うこともありました、／「絶対に最後まで諦めないけど現実的には無理、？」」
2枚目：「でも今は声を大にして言えます。／そんなことない！！大丈夫です！／私は地方大学出身で、特別な実績はありません。コンペの賞歴もとても小規模なものが1つだけ／少しでも、あの頃の私と同じように悩む方の力になれたらうれしいです！🎀」

# 出力形式（JSONのみ。前後に説明を書かない）
{{"main": "1枚目の本文", "reply": "返信につなげる2枚目の本文（URLなし）"}}"""


def load_env_value(name):
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return ""


def notify(title, message):
    """携帯へのプッシュ通知（ntfy）。失敗しても本体の動きは止めない。"""
    topics = [t.strip() for t in load_env_value("NTFY_TOPIC").split(",") if t.strip()]
    for topic in topics:
        try:
            body = json.dumps({
                "topic": topic, "title": title, "message": message,
                "click": "https://threads.210-131-223-173.sslip.io/", "tags": ["pencil"],
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request("https://ntfy.sh", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"通知失敗（無視して続行）: {e}")


FALLBACK_MODELS = [MODEL, "gemini-3.6-flash", "gemini-3.5-flash"]  # 混雑時はこの順で切り替える


def call_gemini(key, prompt):
    """Geminiを呼ぶ。混雑エラー（503/429等）は再試行し、だめなら予備モデルに切り替える。"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    last_err = None
    for model in FALLBACK_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        for attempt in range(2):
            if attempt:
                print(f"  混雑のため45秒待って再試行（{model}）")
                time.sleep(45)
            try:
                req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                             headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = json.loads(res.read().decode("utf-8"))
                return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code not in (429, 500, 502, 503, 504):
                    raise
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
        print(f"  {model} がだめなので予備モデルへ切り替え")
    raise last_err


def run():
    """生成の本体。失敗したら例外を投げる（main側で通知する）。"""
    target = date.today() + timedelta(days=1)
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        target = date.fromisoformat(sys.argv[1])
    out_path = DRAFTS_DIR / f"{target.isoformat()}.json"
    if out_path.exists() and "--force" not in sys.argv:
        print(f"スキップ: {out_path} は既に存在します（承認状態を守るため上書きしません。作り直すときは --force）")
        return
    key = load_key()
    articles = parse_ledger()
    history = load_history()
    a_no, p_no = pick_articles(articles, history, target)

    drafts = {"date": target.isoformat(), "posts": []}
    used_in_run = {}
    for slot, no in (("morning", a_no), ("evening", p_no)):
        art = articles[no]
        prompt = build_prompt(art, slot, target) + top_posts_reference(history)
        out = call_gemini(key, prompt)
        for _ in range(2):  # 見た目ルール・？終わりの違反があれば最大2回書き直させる
            probs = layout_problems(out["main"]) + layout_problems(out["reply"])
            q_end = out["main"].rstrip("🌸✨😢🙏🏻🫧 ").rstrip().endswith(("？", "?"))
            if not probs and not q_end:
                break
            fb = "、".join(f"「{p}…」の段落（最終行が全角{w:.0f}文字）" for p, w in probs)
            extra = "。1枚目の最後が疑問符『？』で終わっている。読点『、』の言いかけか、含みのある句点『。』の余韻に直すこと" if q_end else ""
            out = call_gemini(key, prompt + f"""

# 書き直し指示
前回の出力は次のルール違反があった：{fb}{extra}。
該当箇所の文末を調整して全体を出し直すこと。内容・構成は変えない。
前回の出力：
{json.dumps(out, ensure_ascii=False)}""")
        remaining = layout_problems(out["main"]) + layout_problems(out["reply"])
        if remaining:
            print(f"  ⚠️ 見た目ルールを満たせなかった段落が{len(remaining)}件あります（承認ページで確認を）")
        hen = HEN_MAP.get(no, "就活編")
        num = hen_number(hen, history, used_in_run)
        used_in_run[hen] = used_in_run.get(hen, 0) + 1
        title = f"【{SERIES_TITLE}｜{hen}{circled(num)}】"
        body = out["main"].strip()
        if body.startswith("【"):  # AIが題名を書いてしまった場合は取り除く
            body = "\n".join(body.splitlines()[1:]).strip()
        main_text = sanitize((title + "\n" + body)[:480])
        out["reply"] = sanitize(out["reply"].strip())
        drafts["posts"].append({
            "slot": slot, "article_no": no, "article_title": art["title"],
            "article_url": art["url"], "hen": hen, "hen_no": num,
            "main": main_text, "reply": out["reply"].strip(),
            "status": "draft",
        })
        print(f"[{slot}] 記事{no}：{art['title']}")
        print(main_text)
        print("(返信) " + out["reply"].strip())
        print("-" * 40)

    DRAFTS_DIR.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存: {out_path}")
    m, d = target.month, target.day
    notify("【リボン】投稿案ができました",
           f"{m}月{d}日の朝・夕2本の下書きができています。タップして承認ページを開き、確認してください。")


def main():
    try:
        run()
    except Exception as e:
        print(f"生成失敗: {type(e).__name__} {str(e)[:200]}")
        notify("【リボン】⚠️ 今夜の投稿案が作れませんでした",
               f"生成中にエラーが起きました（{type(e).__name__}）。自動再試行もだめだったため、明日の下書きはまだありません。管理者に連絡してください。")
        raise


if __name__ == "__main__":
    main()
