#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析JSON（BUN-…json）から、人が読むHTMLを作る。

⚠️ **なぜこの道具があるか**
   HTMLとJSONを別々に書くと、必ず食い違う。「同じ1回の分析から2つ出す」と
   決めても、人（AI）が2回書けば2回考えることになる。
   **だからHTMLは書かない。JSONから機械が作る。**
   これで「HTMLにJSONに無い独自解釈を足す」ことが**原理的に起きない。**

⚠️ **ここに分析の中身を1文字も書かない。**
   このファイルにあるのは、見出しの言葉と並べ方だけ。
   数字・仕事・仮説・注意書きは、すべてJSONから読む。
   ここに文章を足したら、それは「JSONに無い独自解釈」になる。

    使い方:  python bun_html.py <BUN-…….json>
             → 同じフォルダに同じ名前の .html を作る
"""
import html
import json
import sys
from pathlib import Path

# 印（確からしさ）の言い換え。⚠️ 判定はしない。JSONの値を日本語にするだけ
SHIRUSHI = {
    "jijitsu":   ("事実",       "ok"),
    "sotei":     ("想定",       "ng"),
    "kasetsu":   ("仮説",       "mi"),
    "mikakunin": ("要確認",     "mi"),
    "sanko":     ("業種の目安", "mi"),
    "yokyu":     ("相談の内容", "ok"),
}
SHURUI = {
    "A":   ("A", "調査・測定", "a"),
    "B":   ("B", "今すぐ安全に実行", "b"),
    "C-1": ("C-1", "数字を待たず・個別承認", "c1"),
    "C-2": ("C-2", "実測後に判断", "c2"),
}
SHIHYO_SHURUI = {"mokuhyo": ("目標", "ok"), "meyasu": ("目安・目標ではない", "mi")}


def e(x):
    return html.escape("" if x is None else str(x))


def shirushi_tag(v):
    if not v:
        return ""
    na, kl = SHIRUSHI.get(v, (v, "mi"))
    return '<span class="b %s">%s</span>' % (kl, e(na))


def ids(lst):
    return "・".join(e(x) for x in (lst or [])) or "—"


def midashi(no, na, soe=""):
    return ('<section><div class="sh"><span class="no">%s</span><h2>%s</h2>'
            '%s</div>' % (e(no), e(na),
                          ('<p class="sub">%s</p>' % e(soe)) if soe else ""))


def tsukuru(d):
    h = []
    a = h.append
    kouho = d.get("shigoto_kouho") or []
    def eda(s):
        return [x for x in kouho if x.get("shurui") == s]

    # ── 頭 ────────────────────────────────────────────
    a('<header><p class="eyebrow">%s ／ %s回目の分析 ／ %s</p>'
      % (e(d.get("bun_id")), e(d.get("ban")), e(d.get("sakusei_bi"))))
    a('<h1>%s</h1>' % e((d.get("mokuteki") or {}).get("bun")))
    a('<p class="lede">%s</p>' % e(d.get("moto_sodan")))
    a('<div class="tags"><span class="tag">対象：%s</span><span class="tag">%s</span>'
      % (e(d.get("taisho_an")), e(d.get("gyoshu"))))
    if not d.get("jitsu_data_kakunin"):
        a('<span class="tag ng">実データ未確認・数字はすべて想定</span>')
    a('</div>')
    a('<p class="oshite">このページは <code>%s</code> から機械が作っています。'
      'ここに書かれていることは、すべて分析データの中にあります。</p></header>'
      % e((d.get("bun_id") or "") + ".json"))

    # ── 目的と目標 ────────────────────────────────────
    mh = d.get("mokuhyo_an") or {}
    a(midashi("01", "目的と目標（案）", "正式な目標になるのは、人が承認したあとです"))
    a('<div class="scroller"><table><tbody>')
    a('<tr><th style="width:16%%">目的</th><td>%s %s</td></tr>'
      % (e((d.get("mokuteki") or {}).get("bun")),
         shirushi_tag((d.get("mokuteki") or {}).get("shirushi"))))
    a('<tr><th>目標（案）</th><td><b>%s</b>　期限 %s %s%s</td></tr>'
      % (e(mh.get("bun")), e(mh.get("kigen")), shirushi_tag(mh.get("shirushi")),
         ('<div class="oshite">%s</div>' % e(mh.get("moto"))) if mh.get("moto") else ""))
    a('</tbody></table></div></section>')

    # ── 現状 ──────────────────────────────────────────
    g = d.get("genjo") or {}
    if g.get("p_l"):
        a(midashi("02", "赤字の形", g.get("moto") or ""))
        a('<div class="scroller"><table><thead><tr><th>費目</th>'
          '<th style="width:16%%">割合</th><th style="width:20%%">金額（%s）</th>'
          '</tr></thead><tbody>' % e(g.get("tani")))
        for r in g["p_l"]:
            kl = " class=\"goukei\"" if r.get("goukei") else (
                 " class=\"keikoku\"" if r.get("keikoku") else "")
            a('<tr%s><td>%s</td><td class="num">%s%%</td><td class="num">%s</td></tr>'
              % (kl, e(r.get("na")), e(r.get("ritsu")), e(r.get("gaku"))))
        a('</tbody></table></div>')
        if g.get("hitsuyo_gaku") is not None:
            a('<div class="box ng"><span class="k">埋めるべき額：%s%s</span>'
              '<p>%s</p></div>'
              % (e(g.get("hitsuyo_gaku")), e(g.get("tani") or ""),
                 e(g.get("moto"))))
        a('</section>')

    # ── 原因仮説 ──────────────────────────────────────
    if d.get("kasetsu"):
        a(midashi("03", "原因の仮説", "それぞれ、どの調査で確かめるかを決めてあります"))
        a('<div class="scroller"><table><thead><tr><th style="width:9%">番号</th>'
          '<th>仮説</th><th style="width:9%">印</th>'
          '<th style="width:20%">確かめる調査</th></tr></thead><tbody>')
        for k in d["kasetsu"]:
            a('<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>'
              % (e(k.get("id")), e(k.get("naiyo")),
                 shirushi_tag(k.get("shirushi")), ids(k.get("kensho"))))
        a('</tbody></table></div></section>')

    # ── 仕事候補 ──────────────────────────────────────
    for s, no, na, soe in (
            ("A", "04", "調査・測定の仕事", "測るだけ。店の運営を何も変えません"),
            ("B", "05", "数字が無くても今すぐ安全に実行する仕事",
             "不可逆でない・お金が動かない・外部に出ない・方針を変えない、の4つをすべて満たすものだけ"),
            ("C-1", "06", "数字を待たないが、個別の承認が要るもの", ""),
            ("C-2", "07", "実測の結果を見てから判断するもの", "")):
        xs = eda(s)
        if not xs:
            continue
        ka, sm, kl = SHURUI[s]
        a(midashi(no, "%s　%s（%d件）" % (ka, na, len(xs)), soe))
        a('<div class="scroller"><table><thead><tr><th style="width:9%">番号</th>'
          '<th style="width:29%">仕事</th><th style="width:9%">不可逆</th>'
          '<th style="width:17%">前提</th><th>なぜ今できるのか／なぜ待つのか</th>'
          '</tr></thead><tbody>')
        for x in xs:
            tani = ('<div class="oshite">単位 %s</div>' % e(x.get("tani"))) if x.get("tani") else ""
            kane = ('<div class="oshite">効き %s万／%s</div>'
                    % (e(x.get("kingaku")), e(x.get("kikime_made")))) if x.get("kingaku") else ""
            jigen = '<span class="b ng">期限あり</span> ' if x.get("jigen") else ""
            yusen = ('<div class="oshite">%s</div>' % e(x.get("yusen"))) if x.get("yusen") else ""
            riyu = e(x.get("riyu"))
            for key in ("konkyo", "zentei_bun", "chui", "moto"):
                if x.get(key):
                    riyu += '<div class="oshite">%s</div>' % e(x[key])
            kk = x.get("kensho_kasetsu")
            if kk:
                riyu += '<div class="oshite">確かめる仮説：<code>%s</code></div>' % e(kk)
            a('<tr><td><code>%s</code></td><td>%s%s%s%s%s</td>'
              '<td class="c">%s</td><td>%s</td><td>%s</td></tr>'
              % (e(x.get("id")), jigen, e(x.get("na")), tani, kane, yusen,
                 '<span class="b ng">はい</span>' if x.get("fukagyaku") else 'いいえ',
                 ids(x.get("zentei")), riyu))
        a('</tbody></table></div></section>')

    # ── 指標 ──────────────────────────────────────────
    if d.get("shihyo_an"):
        a(midashi("08", "測る数字（案）", "目標と目安は別物です"))
        a('<div class="scroller"><table><thead><tr><th style="width:7%">番号</th>'
          '<th style="width:15%">名前</th><th style="width:8%">単位</th>'
          '<th style="width:8%">頻度</th><th style="width:15%">目標（案）</th>'
          '<th style="width:13%">種類</th><th style="width:9%">もとの仕事</th>'
          '<th>完了の判定</th></tr></thead><tbody>')
        for k in d["shihyo_an"]:
            sn, sk = SHIHYO_SHURUI.get(k.get("shurui"), (k.get("shurui"), "mi"))
            chui = ('<div class="oshite">%s</div>' % e(k.get("chui"))) if k.get("chui") else ""
            a('<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td>'
              '<td>%s %s</td><td><span class="b %s">%s</span>%s</td>'
              '<td><code>%s</code></td><td>%s</td></tr>'
              % (e(k.get("id")), e(k.get("na")), e(k.get("tani")), e(k.get("hindo")),
                 e(k.get("mokuhyo_an")), shirushi_tag(k.get("shirushi")),
                 sk, e(sn), chui, e(k.get("moto_shigoto")),
                 # ⚠️ **測定が終わった条件**であって、目標を達成した条件ではない
                 e(k.get("kanryo_hantei"))))
        a('</tbody></table></div></section>')

    # ── フェーズ ──────────────────────────────────────
    if d.get("phase"):
        a(midashi("09", "進める順番", "日数は目安です。次へ進むのは条件で決めます"))
        for p in d["phase"]:
            a('<div class="dan"><div class="midashi"><span class="n">%s</span>%s'
              '<span class="oshite">　%s</span></div>'
              % (e(p.get("no")), e(p.get("na")), e(p.get("meyasu"))))
            a('<div>仕事：%s</div>' % ids(p.get("shigoto")))
            a('<div class="han"><b>次へ進んでよい条件：</b>%s</div></div>'
              % e(p.get("tsugi_e_no_joken")))
        a('</section>')

    # ── 中止条件 ──────────────────────────────────────
    if d.get("chushi_joken"):
        a(midashi("10", "やめる・閉じるの判断"))
        a('<ul>%s</ul></section>'
          % "".join('<li>%s</li>' % e(x) for x in d["chushi_joken"]))

    # ── Gate ──────────────────────────────────────────
    gt = d.get("gate") or {}
    if gt:
        a(midashi("11", "人が判断する3か所"))
        a('<div class="scroller"><table><thead><tr><th style="width:12%">Gate</th>'
          '<th style="width:12%">件数</th><th>何を承認するか</th></tr></thead><tbody>')
        for key in ("gate1", "gate2", "gate3"):
            v = gt.get(key) or {}
            soe = ""
            for k2 in ("c1", "c2"):
                if v.get(k2):
                    soe += '<div class="oshite">%s</div>' % e(v[k2])
            a('<tr><td><b>%s</b></td><td class="c">%s</td><td>%s%s</td></tr>'
              % (e(key.replace("gate", "Gate")),
                 e(v.get("kensu")) if v.get("kensu") is not None else "—",
                 e(v.get("setsumei")), soe))
        a('</tbody></table></div></section>')

    # ── 再分析の条件 ──────────────────────────────────
    if d.get("saibunseki_joken"):
        a(midashi("12", "もう一度分析し直す条件"))
        a('<ul>%s</ul></section>'
          % "".join('<li>%s</li>' % e(x) for x in d["saibunseki_joken"]))

    # ── 注意 ──────────────────────────────────────────
    if d.get("chui"):
        a('<footer>%s' % "".join('<p>%s</p>' % e(x) for x in d["chui"]))
        a('<p>このページは <code>%s</code> から機械が作りました。'
          '数字を直すときはJSONを直します。</p></footer>' % e((d.get("bun_id") or "") + ".json"))
    return "\n".join(h)


CSS = """
:root{--paper:#F3F4EF;--surface:#fff;--surface2:#EBEEE5;--ink:#191C1A;--ink2:#4C534E;
 --ink3:#79817B;--line:#D6DAD0;--line2:#B4BAAE;--ok:#2F6B4C;--ok-bg:#DBE8E0;
 --ng:#A8332B;--ng-bg:#EEDBD7;--mi:#8A6A16;--mi-bg:#F6EBD2;--acc:#25506B}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --paper:#121513;--surface:#1A1E1B;--surface2:#232823;--ink:#E9ECE5;--ink2:#A7AFA8;
 --ink3:#7C847D;--line:#2C322D;--line2:#434A43;--ok:#7CC79C;--ok-bg:#1C2E23;
 --ng:#E58272;--ng-bg:#3B211C;--mi:#D8B45E;--mi-bg:#332A16;--acc:#7FB3D0}}
:root[data-theme="dark"]{--paper:#121513;--surface:#1A1E1B;--surface2:#232823;--ink:#E9ECE5;
 --ink2:#A7AFA8;--ink3:#7C847D;--line:#2C322D;--line2:#434A43;--ok:#7CC79C;--ok-bg:#1C2E23;
 --ng:#E58272;--ng-bg:#3B211C;--mi:#D8B45E;--mi-bg:#332A16;--acc:#7FB3D0}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
 font-family:"BIZ UDPGothic","Yu Gothic UI","Meiryo",sans-serif;font-size:15px;line-height:1.8}
.wrap{max-width:1080px;margin:0 auto;padding:0 18px 90px}
header{padding:38px 0 20px;border-bottom:3px solid var(--ink);margin-bottom:6px}
.eyebrow{font-size:12px;letter-spacing:.12em;color:var(--ink3);margin:0 0 10px}
h1{font-size:clamp(22px,4vw,32px);line-height:1.4;margin:0 0 12px;text-wrap:balance}
.lede{color:var(--ink2);max-width:64ch;margin:0 0 14px}
.tags{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px}
.tag{font-size:12px;border:1px solid var(--line2);border-radius:3px;padding:3px 9px;
 color:var(--ink2);background:var(--surface)}
.tag.ng{border-color:var(--ng);color:var(--ng);background:var(--ng-bg)}
h2{font-size:19px;line-height:1.45;margin:0;text-wrap:balance}
section{padding:30px 0 6px;border-top:1px solid var(--line)}
.sh{display:flex;align-items:baseline;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.no{font-size:12.5px;color:var(--ink3);letter-spacing:.08em;padding-top:4px;white-space:nowrap}
.sub{font-size:13px;color:var(--ink3);margin:0}
p{margin:0 0 .9em;max-width:66ch}
.oshite{font-size:12.5px;color:var(--ink3);line-height:1.6;margin-top:2px}
.scroller{overflow-x:auto;border:1px solid var(--line);background:var(--surface);margin:12px 0}
table{border-collapse:collapse;width:100%;min-width:620px;font-size:13.5px}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:var(--surface2);color:var(--ink2);font-weight:700;font-size:12.5px;
 border-bottom:1px solid var(--line2);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
td.c{text-align:center;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.goukei td{border-top:2px solid var(--ink);font-weight:700;color:var(--ng)}
tr.keikoku td{background:var(--ng-bg);font-weight:700}
.b{display:inline-block;padding:1px 8px;border-radius:3px;font-size:12px;font-weight:700;white-space:nowrap}
.b.ok{background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok)}
.b.ng{background:var(--ng-bg);color:var(--ng);border:1px solid var(--ng)}
.b.mi{background:var(--mi-bg);color:var(--mi);border:1px solid var(--mi)}
.box{border-left:4px solid var(--acc);background:var(--surface);padding:13px 16px;margin:14px 0}
.box.ng{border-left-color:var(--ng);background:var(--ng-bg)}
.box .k{font-weight:700;display:block;margin-bottom:3px}
.box p{margin:0;max-width:64ch}
ul{margin:6px 0 12px;padding-left:1.2em}
li{margin:0 0 5px;max-width:64ch}
code{font-family:Consolas,monospace;font-size:.9em;background:var(--surface2);padding:1px 5px;border-radius:3px}
.dan{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--acc);
 padding:12px 16px;margin:12px 0}
.dan .midashi{font-size:16px;font-weight:700;margin-bottom:4px}
.dan .midashi .n{color:var(--acc);margin-right:8px}
.dan .han{background:var(--ok-bg);border-left:3px solid var(--ok);padding:7px 11px;
 margin-top:8px;font-size:13.5px}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
 font-size:13px;color:var(--ink3)}
"""


def main():
    if len(sys.argv) < 2:
        print("使い方: python bun_html.py <BUN-…….json>")
        return 1
    p = Path(sys.argv[1])
    d = json.loads(p.read_text(encoding="utf-8"))
    naka = tsukuru(d)
    title = "%s　%s" % (d.get("bun_id"), (d.get("mokuteki") or {}).get("bun") or "")
    out = p.with_suffix(".html")
    out.write_text(
        '<!DOCTYPE html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="bun-id" content="%s">\n<title>%s</title>\n<style>%s</style>\n'
        '</head>\n<body>\n<div class="wrap">\n%s\n</div>\n</body>\n</html>\n'
        % (e(d.get("bun_id")), e(title), CSS, naka), encoding="utf-8")
    print("作りました: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
