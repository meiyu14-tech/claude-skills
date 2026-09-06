#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""再分析の材料を、仕事の基本アプリから取ってくる（境界6・2026-09-06）。

⚠️ **人がコピペしない。**画面を見て書き写す運用にしない。
⚠️ **正本を複製保存しない。**取ってきたものは、その場の再分析の材料にするだけ。
   ここで作ったファイルは、あくまで分析するときの下書き置き場。
⚠️ 合言葉は環境変数から（bun_okuru.py と同じ決まり）。
   受付と同じ機械の中（localhost）から呼ぶときだけ、名乗りを直接付ける。

    使い方:  python bun_zairyo.py <PRJ-…>            ← 画面に出す
             python bun_zairyo.py <PRJ-…> --file X   ← Xへ書き出す
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

SAKI = os.environ.get("KIHON_URL") or "https://map.210-131-223-173.sslip.io/kihon-api"


def uchigawa(url):
    return "127.0.0.1" in url or "localhost" in url


def toru(michi):
    user = os.environ.get("KIHON_USER")
    if not user:
        print("⚠️ 環境変数 KIHON_USER（ログイン名）を入れてください。")
        return None
    r = urllib.request.Request(SAKI.rstrip("/") + michi)
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
        print("⚠️ 取れませんでした： HTTP %d %s"
              % (ex.code, ex.read().decode("utf-8", "replace")[:200]))
        return None
    except Exception as ex:
        print("⚠️ 取れませんでした： %s" % type(ex).__name__)
        return None


def main():
    if len(sys.argv) < 2:
        print("使い方: python bun_zairyo.py <PRJ-…> [--file 書き出し先]")
        return 1
    pid = sys.argv[1]
    d = toru("/saibunseki-zairyo?prj=" + urllib.parse.quote(pid))
    if d is None:
        return 1
    if "--file" in sys.argv:
        p = sys.argv[sys.argv.index("--file") + 1]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print("材料を書き出しました： %s" % p)
    else:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    ji = d.get("jisseki") or []
    dekiru = [x for x in ji if (x.get("hikaku") or {}).get("jotai") == "hikaku_kanou"]
    print("\n── 材料のあらまし ──", file=sys.stderr)
    print("  元の分析： %s ／ プロジェクト： %s"
          % ("・".join(d.get("moto_bun") or []), d.get("prj_id")), file=sys.stderr)
    print("  仕事： %d件（実行済み %d／未実行 %d）"
          % (len(d.get("shigoto") or []), len(d.get("jikko_sumi") or []),
             len(d.get("mi_jikko") or [])), file=sys.stderr)
    print("  実績の行： %d件（うち比較できた %d件）" % (len(ji), len(dekiru)), file=sys.stderr)
    print("  そろえば比較できるもの： %s" % (d.get("iru_kijun") or "なし"), file=sys.stderr)
    print("  評価OSの記録： %d件%s"
          % (len(d.get("hyoka") or []),
             ("／" + d["hyoka_error"]) if d.get("hyoka_error") else ""), file=sys.stderr)
    return 0


import urllib.parse  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
