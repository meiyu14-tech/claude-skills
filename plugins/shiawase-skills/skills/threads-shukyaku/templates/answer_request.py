# -*- coding: utf-8 -*-
"""娘さんの要望に回答する（Claudeが対応後に実行）。
使い方：python3 answer_request.py <要望id> "回答文"
requests.jsonl の該当要望を status:done・answer:回答 に更新し、娘さんの携帯へ通知する。
承認ページの要望欄に回答が表示される。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = Path(os.environ.get("THREADS_HOME", Path(__file__).resolve().parent))


def env():
    conf = {}
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def main():
    if len(sys.argv) < 3:
        print('使い方: python3 answer_request.py <要望id> "回答文"')
        print("--- 未対応の要望一覧 ---")
        f = BASE / "requests.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("status") != "done":
                    print(f"{r.get('id')} | {r.get('at','')[:16]} | {r.get('text','')}")
        return
    rid, ans = sys.argv[1], sys.argv[2]
    f = BASE / "requests.jsonl"
    lines = f.read_text(encoding="utf-8").splitlines()
    out, found = [], False
    for line in lines:
        try:
            r = json.loads(line)
        except Exception:
            out.append(line)
            continue
        if r.get("id") == rid:
            r["status"] = "done"
            r["answer"] = ans
            found = True
        out.append(json.dumps(r, ensure_ascii=False))
    f.write_text("\n".join(out) + "\n", encoding="utf-8")
    if not found:
        print(f"⚠️ id {rid} が見つかりませんでした")
        return
    conf = env()
    name = conf.get("INSTANCE_NAME", "")
    for topic in [t.strip() for t in conf.get("NTFY_TOPIC", "").split(",") if t.strip()]:
        try:
            body = json.dumps({"topic": topic, "title": f"【{name}】要望への回答が届きました",
                               "message": ans[:160], "click": "https://" + conf.get("APPROVAL_HOST", "") + "/",
                               "tags": ["white_check_mark"]}, ensure_ascii=False).encode()
            urllib.request.urlopen(urllib.request.Request("https://ntfy.sh", data=body,
                                   headers={"Content-Type": "application/json"}), timeout=15)
        except Exception:
            pass
    print(f"回答を保存し通知しました（id {rid}）")


if __name__ == "__main__":
    main()
