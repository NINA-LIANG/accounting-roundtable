#!/usr/bin/env python3
"""資料更新驗證：確認 12 部法規都在、條數合理、最近同步成功，並抽查條文與官方單條頁面逐字比對。
用法：python3 verify_kb.py   結果寫入 verify_log.csv，並印出 JSON。全部通過時結束碼 0，否則 1。"""
import csv, html, json, os, random, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TZ = timezone(timedelta(hours=8))
EXPECT = 30
MAX_AGE_DAYS = 7  # 憲章發布關卡②：超過 7 天未同步即不通過

def norm(s):
    return re.sub(r"[\s　，。、；：「」『』（）()〔〕.,;:\-－—]", "", s)

def official_text(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (law-kb-verify)"})
            page = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
            m = re.search(r'<div class="law-article">(.*?)</div>\s*</div>', page, re.S)
            body = m.group(1) if m else page
            return html.unescape(re.sub(r"<[^>]+>", "", body))
        except Exception as e:
            last = e; time.sleep(2 ** (i + 1))
    raise last

def main():
    now = datetime.now(TZ)
    idx = json.load(open(os.path.join(HERE, "index.json"), encoding="utf8"))
    problems, checked, total = [], [], 0
    laws = idx.get("laws", [])
    if len(laws) != EXPECT:
        problems.append(f"法規數 {len(laws)}，應為 {EXPECT}")
    if idx.get("errors"):
        problems.append(f"上次同步有失敗：{idx['errors']}")
    synced = datetime.fromisoformat(idx["syncedAt"].replace("+0800", "+08:00"))
    age = (now - synced).total_seconds() / 86400
    if age > MAX_AGE_DAYS:
        problems.append(f"距上次同步 {age:.1f} 天，超過 {MAX_AGE_DAYS} 天")
    for l in laws:
        d = json.load(open(os.path.join(HERE, "laws", l["pcode"] + ".json"), encoding="utf8"))
        arts = d["articles"]; total += len(arts)
        if not arts:
            problems.append(f"{d['name']} 沒有條文"); continue
        a = random.choice(arts)
        try:
            ok = norm(a["text"]) in norm(official_text(a["url"]))
        except Exception as e:
            ok = None; problems.append(f"{d['name']} 第 {a['no']} 條抽查抓取失敗：{e}")
        if ok is False:
            problems.append(f"{d['name']} 第 {a['no']} 條與官方頁面不一致")
        checked.append({"law": d["name"], "no": a["no"], "match": ok, "url": a["url"]})
        time.sleep(0.5)
    result = {"checkedAt": now.isoformat(timespec="seconds"), "syncedAt": idx["syncedAt"], "ageDays": round(age, 2),
              "laws": len(laws), "articles": total, "spotChecks": checked, "problems": problems, "pass": not problems}
    log = os.path.join(HERE, "verify_log.csv"); new = not os.path.exists(log)
    with open(log, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["驗證時間", "上次同步", "距今天數", "法規數", "條文總數", "抽查一致數", "抽查總數", "是否通過", "問題"])
        w.writerow([result["checkedAt"], idx["syncedAt"], result["ageDays"], len(laws), total,
                    sum(1 for c in checked if c["match"]), len(checked), "通過" if result["pass"] else "不通過", "；".join(problems)])
    print(json.dumps(result, ensure_ascii=False, indent=1))
    sys.exit(0 if result["pass"] else 1)

if __name__ == "__main__":
    main()
