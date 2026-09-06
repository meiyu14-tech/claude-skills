#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析JSONとHTMLを突き合わせて検査する。

⚠️ **なぜ要るか**
   「HTMLはJSONから作る」と決めても、**決めただけでは守られない**（運用ルール第5条）。
   通らないと配れない形にするため、機械が確かめる。

検査するもの
    1 IDが同じ          JSONの bun_id と HTMLの <meta name="bun-id"> が一致
    2 数字が食い違わない  JSONの数値が、HTMLにすべて出ている
    3 必須項目が欠けない  契約で必須と決めた欄が全部ある
    4 独自解釈が無い      HTMLの日本語のうち、JSONにもラベル表にも無いものが無い
    5 分析の中身が薄くない 仕事・仮説・指標・フェーズの件数が下限以上

    使い方:  python bun_kensa.py <BUN-…….json>
"""
import json
import re
import sys
from pathlib import Path

# 本文を切り分ける区切り。⚠️ ラベル表もHTMLも**同じ切り方**にする（食い違わせない）
KUGIRI = r"[／・（）「」【】　 ,.:：、。0-9A-Za-z%△+-]+"

# レンダラーが持つ固定の言葉（分析の中身ではない）。⚠️ ここに分析の文章を足さない。
# ⚠️ レンダラーの言い回しを変えたら、ここにも足す。**足すまで検査4は落ち続ける**（それでよい）
LABEL_RAW = """
期限 件 単位 頻度 種類 印 完了の判定 もとの仕事
"""
LABEL_HON = """
目的 目標 案 対象 費目 割合 金額 番号 仮説 印 確かめる調査 仕事 不可逆 前提
なぜ今できるのか なぜ待つのか 名前 単位 頻度 種類 もとの仕事 件数 何を承認するか
事実 想定 要確認 業種の目安 相談の内容 目安 目標ではない 調査 測定 今すぐ安全に実行
数字を待たず 個別承認 実測後に判断 期限あり はい いいえ 回目の分析
このページは から機械が作っています ここに書かれていることは すべて分析データの中にあります
埋めるべき額 単位 万 効き 確かめる仮説 次へ進んでよい条件 進める順番
日数は目安です 次へ進むのは条件で決めます 人が判断する3か所 やめる 閉じるの判断
もう一度分析し直す条件 測る数字 目標と目安は別物です 赤字の形 原因の仮説
それぞれ どの調査で確かめるかを決めてあります 実データ未確認 数字はすべて想定
正式な目標になるのは 人が承認したあとです 測るだけ 店の運営を何も変えません
不可逆でない お金が動かない 外部に出ない 方針を変えない の4つをすべて満たすものだけ
数字を待たないが 個別の承認が要るもの 実測の結果を見てから判断するもの
数字が無くても今すぐ安全に実行する仕事 調査 測定の仕事 目的と目標
数字を直すときはJSONを直します から機械が作りました
"""
# ⚠️ ラベル表も本文と**同じ切り方**で刻む。切り方が違うと、同じ言葉が別物になる
LABEL = {w for w in re.split(KUGIRI + r"|\s+", LABEL_HON + LABEL_RAW) if w}

# 契約で必須と決めた欄（4者間データ契約・境界1）
HISSU = ["bun_id", "ban", "sakusei_bi", "moto_sodan", "taisho_an",
         "mokuteki", "mokuhyo_an", "kasetsu", "shigoto_kouho",
         "shihyo_an", "phase", "gate", "hikiwatashi"]
HISSU_SHIGOTO = ["id", "shurui", "na", "fukagyaku", "gate", "riyu"]
HISSU_SHIHYO = ["id", "na", "tani", "hindo", "shurui"]
SHURUI_OK = {"A", "B", "C-1", "C-2"}

KEKKA = []


def t(na, ok, memo=""):
    KEKKA.append((na, bool(ok), memo))
    print("  %s %-46s %s" % ("PASS" if ok else "FAIL", na, memo))


def moji_atsume(o, out):
    """JSONの中の文字列と数値を全部集める"""
    if isinstance(o, dict):
        for k, v in o.items():
            moji_atsume(v, out)
    elif isinstance(o, list):
        for v in o:
            moji_atsume(v, out)
    elif isinstance(o, str):
        out.add(o.strip())
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out.add(str(o))
        if isinstance(o, int) and o < 0:
            out.add(str(-o))          # HTMLでは △200 のように符号を分けて出る場合がある
    return out


def main():
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "")
    if not p.exists():
        print("使い方: python bun_kensa.py <BUN-…….json>")
        return 1
    d = json.loads(p.read_text(encoding="utf-8"))
    h = p.with_suffix(".html")
    if not h.exists():
        print("HTMLがありません: %s" % h)
        return 1
    html = h.read_text(encoding="utf-8")

    print("\n分析の検査： %s\n" % p.name)

    # 1 IDが同じ
    m = re.search(r'<meta name="bun-id" content="([^"]+)"', html)
    t("1 IDが同じ", m and m.group(1) == d.get("bun_id"),
      "JSON %s ／ HTML %s" % (d.get("bun_id"), m.group(1) if m else "なし"))

    # 2 数字が食い違わない（JSONの数値がHTMLに出ているか）
    suuji = set()
    moji_atsume(d, suuji)
    kazu = [x for x in suuji if re.fullmatch(r"-?\d+(\.\d+)?", x)]
    nai = [x for x in kazu if x.lstrip("-") not in html]
    t("2 数字が食い違わない", not nai,
      "数値 %d件すべてHTMLにある" % len(kazu) if not nai else "HTMLに無い数値: %s" % nai[:5])

    # 3 必須項目が欠けない
    kake = [k for k in HISSU if not d.get(k)]
    for x in d.get("shigoto_kouho") or []:
        for k in HISSU_SHIGOTO:
            if k not in x:
                kake.append("%s.%s" % (x.get("id"), k))
        if x.get("shurui") not in SHURUI_OK:
            kake.append("%s.shurui=%s" % (x.get("id"), x.get("shurui")))
    for x in d.get("shihyo_an") or []:
        for k in HISSU_SHIHYO:
            if k not in x:
                kake.append("%s.%s" % (x.get("id"), k))
    t("3 必須項目が欠けない", not kake,
      "欠け無し" if not kake else "欠け: %s" % kake[:6])

    # 4 HTMLにJSONに無い独自解釈が無い
    honbun = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    honbun = re.sub(r"<[^>]+>", "\n", honbun)
    # ⚠️ 1行にラベルとJSONの値が混ざる（例「対象：知り合いの社長のパン屋」）。
    #    そこで **JSONの値をその行から全部取り除き、残りがラベルだけか**を見る。
    #    残りに日本語が残ったら、それは JSON にもラベル表にも無い文＝独自解釈。
    # ⚠️ **数字そのものは取り除かない。**JSONに 4 があるだけで「の4つを」から4が消え、
    #    ラベルが別の言葉に化ける（2026-09-06 実際に起きた）。数字はKUGIRIで区切る。
    #    文字の値は1文字でも取り除く（例「円」）。
    atai = sorted((v for v in suuji
                   if v and not re.fullmatch(r"-?\d+(\.\d+)?", v)),
                  key=len, reverse=True)
    hoka = []
    for gyo in honbun.split("\n"):
        s = gyo.strip()
        if not s or not re.search(r"[ぁ-んァ-ヶ一-龥]", s):
            continue
        for v in atai:
            if v in s:
                s = s.replace(v, "")
        nokori = [w for w in re.split(KUGIRI, s) if w]
        nokori = [w for w in nokori if w not in LABEL]
        if not nokori:
            continue
        hoka.append(gyo.strip()[:60] + " ／ 残り: " + "".join(nokori)[:30])
    t("4 独自解釈が無い", not hoka,
      "JSONに無い文が0件" if not hoka else "JSONに無い文: %s" % hoka[:4])

    # 5 分析の中身が薄くない
    k = d.get("shigoto_kouho") or []
    n = {s: len([x for x in k if x.get("shurui") == s]) for s in SHURUI_OK}
    usui = []
    if n["A"] < 10:
        usui.append("調査A %d件" % n["A"])
    if n["B"] < 5:
        usui.append("即実行B %d件" % n["B"])
    if n["C-1"] + n["C-2"] < 8:
        usui.append("候補C %d件" % (n["C-1"] + n["C-2"]))
    if len(d.get("kasetsu") or []) < 3:
        usui.append("仮説 %d件" % len(d.get("kasetsu") or []))
    if len(d.get("shihyo_an") or []) < 3:
        usui.append("指標 %d件" % len(d.get("shihyo_an") or []))
    if len(d.get("phase") or []) < 3:
        usui.append("フェーズ %d件" % len(d.get("phase") or []))
    t("5 分析の中身が薄くない", not usui,
      "A%d／B%d／C-1が%d／C-2が%d／仮説%d／指標%d／フェーズ%d"
      % (n["A"], n["B"], n["C-1"], n["C-2"], len(d.get("kasetsu") or []),
         len(d.get("shihyo_an") or []), len(d.get("phase") or []))
      if not usui else "薄い: %s" % usui)

    ok = sum(1 for _, o, _ in KEKKA if o)
    print("\n" + "=" * 60)
    print("  %d件 / PASS %d / FAIL %d" % (len(KEKKA), ok, len(KEKKA) - ok))
    print("=" * 60)
    return 0 if ok == len(KEKKA) else 1


if __name__ == "__main__":
    sys.exit(main())
