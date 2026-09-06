#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析JSON（BUN-…json）を、仕事の基本アプリへ送る（境界1・2026-09-06）。

⚠️ **人がコピペしない。**JSONを開いて別の画面へ貼り付ける運用にしない。
   ここが機械で送る通り道。

⚠️ **合言葉をコードに書かない。**環境変数から読む。
       KIHON_USER … ログイン名（例 ito）
       KIHON_PASS … パスワード
   どちらか無ければ、**送らずに止まる**（間違えて素通りしない）。
   ⚠️ 画面にもログにも、パスワードを1文字も出さない。

⚠️ **同じ分析を2回送っても増えない。**受け側が「すでにある」と返す。
   送り直しは起きるもの（通信が切れた・確かめたい）なので、送る側で防がない。
   **受け側で防ぐ。**（送る側で防ぐと、送る道が増えたときに漏れる）

    使い方:  python bun_okuru.py <BUN-…….json>
             python bun_okuru.py <BUN-…….json> --shimesu   ← 送らずに中身だけ見る
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 日本語が化ける端末でも止まらないように

SAKI = os.environ.get("KIHON_URL") or "https://map.210-131-223-173.sslip.io/kihon-api"


def nayose(bun):
    """⚠️ 送るのは、②が実行に必要な部分だけ（4者間データ契約・境界1）。

    ⚠️ 渡さないもの：想定P/Lの全体・原因仮説の全文・業種の目安・金額の計算過程。
       これらは①に残し、②は src_id と分析IDで指すだけ。
    """
    return {
        "bun_id": bun.get("bun_id"),
        "ban": bun.get("ban"),
        "mae_bun_id": bun.get("mae_bun_id"),
        "taisho_an": bun.get("taisho_an"),
        "mokuteki": bun.get("mokuteki"),
        "mokuhyo_an": bun.get("mokuhyo_an"),
        # 仕事候補は Gate1 のものだけ。⚠️ C-1／C-2 はここでは正式化しない
        "shigoto_kouho": [x for x in (bun.get("shigoto_kouho") or [])
                          if x.get("gate") == "gate1"],
        "shihyo_an": bun.get("shihyo_an"),
    }


def uchigawa(url):
    """受付のすぐ隣（localhost）から送るか。⚠️ その場合だけ合言葉が要らない。"""
    return "127.0.0.1" in url or "localhost" in url


def okuru(michi, karada):
    user = os.environ.get("KIHON_USER")
    if not user:
        print("⚠️ 送れません。環境変数 KIHON_USER（ログイン名）を入れてください。")
        return None
    r = urllib.request.Request(SAKI.rstrip("/") + michi,
                               data=json.dumps(karada, ensure_ascii=False).encode("utf-8"))
    r.add_header("Content-Type", "application/json")
    if uchigawa(SAKI):
        # ⚠️ 受付と同じ機械の中から送るとき。nginxを通らないので名乗りを直接付ける。
        #    **これは仕事の基本アプリで既に使っている道**（呼び出しの口も同じ形）。
        #    ⚠️ 外から来る道では絶対にこれを使わない（自己申告になるため）。
        r.add_header("X-Remote-User", user)
    else:
        pw = os.environ.get("KIHON_PASS")
        if not pw:
            print("⚠️ 送れません。環境変数 KIHON_PASS を入れてください。")
            print("   （合言葉はコードに書きません。画面にも出しません）")
            return None
        r.add_header("Authorization", "Basic " + base64.b64encode(
            ("%s:%s" % (user, pw)).encode("utf-8")).decode("ascii"))
    try:
        with urllib.request.urlopen(r, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        honbun = ex.read().decode("utf-8", "replace")[:300]
        # ⚠️ ここにパスワードは出さない
        print("⚠️ 送れませんでした： HTTP %d %s" % (ex.code, honbun))
        if ex.code == 401:
            print("   ログイン名かパスワードが違います（環境変数を確かめてください）")
        return None
    except Exception as ex:
        print("⚠️ 送れませんでした： %s" % type(ex).__name__)
        return None


def main():
    if len(sys.argv) < 2:
        print("使い方: python bun_okuru.py <BUN-…….json> [--shimesu]")
        return 1
    p = Path(sys.argv[1])
    if not p.exists():
        print("分析データがありません: %s" % p)
        return 1
    bun = json.loads(p.read_text(encoding="utf-8"))
    okuru_mono = nayose(bun)

    kazu = len(okuru_mono["shigoto_kouho"] or [])
    print("送るもの： %s ／ Gate1の仕事 %d件 ／ 指標 %d件"
          % (okuru_mono["bun_id"], kazu, len(okuru_mono["shihyo_an"] or [])))
    print("送り先： %s" % SAKI)

    if "--shimesu" in sys.argv:
        print("（--shimesu なので送っていません）")
        return 0

    r = okuru("/prj-tsukuru", {"bun": okuru_mono})
    if r is None:
        return 1
    if r.get("sude_ni"):
        print("○ すでにありました： %s（仕事 %d件・何も増やしていません）"
              % (r.get("prj"), len(r.get("job") or [])))
    else:
        print("○ 作りました： %s（左に入れた仕事 %d件・指標 %d件）"
              % (r.get("prj"), r.get("hidari_ni_ireta"), len(r.get("shihyo") or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
