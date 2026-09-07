#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""すでに登録済みの仕事へ、あとから足りないものを埋める（2026-09-07）。

    ① 完了の判定   kanryo-hantei_<BUN-ID>.json
    ② だれが行うか yakuwari_<BUN-ID>.json


⚠️ **なぜ要るか**
   初回分析で仕事の完了の判定を出し漏らし、**25件が「まだ書かれていません」のまま
   本番の画面に並んだ。**完了の判定を必ず出す決まりは作ってあったのに、
   対象を指標だけにして仕事へ広げなかったのが原因。

⚠️ **前の分析は書き換えない。**後から出したものは、隣の
   「kanryo-hantei_<BUN-ID>.json」に置き、ここから機械で送る。
⚠️ **空いている欄だけ埋まる。**すでに入っているものは②が触らない。
⚠️ 人がコピペしない。合言葉は環境変数から（bun_okuru.py と同じ決まり）。

    使い方:  python bun_oginau.py <補いの台帳.json> [--shimesu]
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
        print("使い方: python bun_oginau.py <補いの台帳.json> [--shimesu]")
        return 1
    p = Path(sys.argv[1])
    if not p.exists():
        print("補いの台帳がありません: %s" % p)
        return 1
    d = json.loads(p.read_text(encoding="utf-8"))
    # どちらの補いかは、中身で決める（人に種類を打たせない）
    if d.get("yakuwari"):
        nakami, michi, na = d["yakuwari"], "/shigoto-yakuwari", "だれが行うか"
        karada = {"bun_id": d.get("bun_id"), "prj": d.get("prj_id"),
                  "yakuwari": nakami}
    elif d.get("kanryo_hantei"):
        nakami, michi, na = d["kanryo_hantei"], "/shigoto-oginau", "完了の判定"
        karada = {"bun_id": d.get("bun_id"), "kanryo_hantei": nakami}
    else:
        print("⚠️ kanryo_hantei も yakuwari も入っていません")
        return 1
    print("送るもの： %s の%s %d件" % (d.get("bun_id"), na, len(nakami)))
    print("送り先： %s" % SAKI)
    print("⚠️ 空いているものだけ入ります。すでに入っているものは触りません。")
    if "--shimesu" in sys.argv:
        print("（--shimesu なので送っていません）")
        return 0
    r = okuru(michi, karada)
    if r is None:
        return 1
    ireta = r.get("umeta") or r.get("ireta") or []
    print("○ 入れました： %d件" % len(ireta))
    if r.get("sude_ni_atta"):
        print("   すでに入っていた（触っていない）： %s" % "・".join(r["sude_ni_atta"]))
    if r.get("moto_ni_nakatta"):
        print("   ⚠️ 補いの台帳に無かった： %s" % "・".join(r["moto_ni_nakatta"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
