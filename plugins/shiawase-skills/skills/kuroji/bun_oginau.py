#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出し漏らした「完了の判定」を、すでに登録済みの仕事へ埋める（2026-09-07）。

⚠️ **なぜ要るか**
   初回分析で仕事の完了の判定を出し漏らし、**25件が「まだ書かれていません」のまま
   本番の画面に並んだ。**完了の判定を必ず出す決まりは作ってあったのに、
   対象を指標だけにして仕事へ広げなかったのが原因。

⚠️ **前の分析は書き換えない。**後から出したものは、隣の
   「kanryo-hantei_<BUN-ID>.json」に置き、ここから機械で送る。
⚠️ **空いている欄だけ埋まる。**すでに入っているものは②が触らない。
⚠️ 人がコピペしない。合言葉は環境変数から（bun_okuru.py と同じ決まり）。

    使い方:  python bun_oginau.py <kanryo-hantei_BUN-…….json> [--shimesu]
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAKI = os.environ.get("KIHON_URL") or "https://map.210-131-223-173.sslip.io/kihon-api"


def uchigawa(url):
    return "127.0.0.1" in url or "localhost" in url


def okuru(michi, karada):
    user = os.environ.get("KIHON_USER")
    if not user:
        print("⚠️ 環境変数 KIHON_USER（ログイン名）を入れてください。")
        return None
    r = urllib.request.Request(
        SAKI.rstrip("/") + michi,
        data=json.dumps(karada, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    if uchigawa(SAKI):
        r.add_header("X-Remote-User", user)
    else:
        pw = os.environ.get("KIHON_PASS")
        if not pw:
            print("⚠️ 環境変数 KIHON_PASS を入れてください。"
                  "（合言葉はコードに書きません。画面にも出しません）")
            return None
        r.add_header("Authorization", "Basic " + base64.b64encode(
            ("%s:%s" % (user, pw)).encode("utf-8")).decode("ascii"))
    try:
        with urllib.request.urlopen(r, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        print("⚠️ 送れませんでした： HTTP %d %s"
              % (ex.code, ex.read().decode("utf-8", "replace")[:200]))
        return None
    except Exception as ex:
        print("⚠️ 送れませんでした： %s" % type(ex).__name__)
        return None


def main():
    if len(sys.argv) < 2:
        print("使い方: python bun_oginau.py <kanryo-hantei_BUN-…….json> [--shimesu]")
        return 1
    p = Path(sys.argv[1])
    if not p.exists():
        print("補いの台帳がありません: %s" % p)
        return 1
    d = json.loads(p.read_text(encoding="utf-8"))
    kh = d.get("kanryo_hantei") or {}
    print("送るもの： %s の完了の判定 %d件" % (d.get("bun_id"), len(kh)))
    print("送り先： %s" % SAKI)
    print("⚠️ 空いている欄だけ埋まります。すでに入っているものは触りません。")
    if "--shimesu" in sys.argv:
        print("（--shimesu なので送っていません）")
        return 0
    r = okuru("/shigoto-oginau", {"bun_id": d.get("bun_id"), "kanryo_hantei": kh})
    if r is None:
        return 1
    print("○ 入れました： %d件" % len(r.get("umeta") or []))
    if r.get("sude_ni_atta"):
        print("   すでに入っていた（触っていない）： %s" % "・".join(r["sude_ni_atta"]))
    if r.get("moto_ni_nakatta"):
        print("   ⚠️ 補いの台帳に無かった： %s" % "・".join(r["moto_ni_nakatta"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
