#!/usr/bin/env python3
"""法規知識庫同步程式。

從全國法規資料庫（law.moj.gov.tw）抓取指定法規的全部條文，拆成逐條資料，
並與上一次的結果比對，產生異動清單（新增／修正／刪除的條文）。

用法：python3 sync_laws.py            # 抓取並更新 kb/laws/*.json、kb/index.json、kb/changes/*.json
產出：
  laws/<pcode>.json   每部法規的逐條資料
  index.json          法規清單、修正日期、條文數、同步時間
  changes/<時間>.json  這次同步偵測到的異動（沒有異動就不產生）
  sync_log.csv        每次同步的紀錄（論文「法規更新即時性」的資料來源）
"""
import csv, hashlib, html, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TZ = timezone(timedelta(hours=8))
LAWS = [
    ("G0340080", "營業稅"), ("G0340081", "營業稅"), ("G0340082", "營業稅"),
    ("G0340003", "所得稅"), ("G0340004", "所得稅"), ("G0340051", "所得稅"),
    ("G0340001", "稽徵與罰則"), ("G0340039", "稽徵與罰則"), ("G0340040", "稽徵與罰則"),
    ("J0080009", "商業會計"), ("J0080010", "商業會計"),
    ("G0380028", "票據"),
    # 2026-11-12 擴充（憲章 v1.1）：薪資與社會保險、外籍移工、其他稅法與公司法
    ("L0060001", "健保"), ("L0060002", "健保"), ("L0060027", "健保"),
    ("N0030020", "勞退"), ("N0030021", "勞退"),
    ("N0050001", "勞保"), ("N0050031", "勞保"), ("N0050021", "勞保"),
    ("N0030001", "勞動基準"), ("N0030002", "勞動基準"),
    ("N0090001", "外籍移工"), ("N0090006", "外籍移工"), ("N0090027", "外籍移工"), ("N0090029", "外籍移工"),
    ("G0340028", "所得稅"), ("G0340115", "所得稅"),
    ("J0040051", "產業創新"), ("J0080001", "公司"),
]
BASE = "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode="


def fetch(pcode):
    req = urllib.request.Request(BASE + pcode, headers={"User-Agent": "Mozilla/5.0 (law-kb-sync)"})
    last = None
    for attempt in range(4):  # 連線偶爾會中斷，最多重試 3 次
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def clean(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\r", "").strip()


def parse(pcode, topic, page):
    name = clean(re.search(r'id="hlLawName"[^>]*>([^<]+)', page).group(1))
    m = re.search(r'id="trLNNDate".*?<td>([^<]+)', page, re.S) or re.search(r'id="trLNODate".*?<td>([^<]+)', page, re.S)
    amended = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    body = page[page.find('class="law-reg-content"'):]
    arts, chapter = [], ""
    for tok in re.finditer(r'<div class="h3[^"]*">(.*?)</div>|<div class="row">(.*?)</div>\s*</div></div>', body, re.S):
        if tok.group(1) is not None:
            chapter = re.sub(r"\s+", " ", clean(tok.group(1)))
            continue
        row = tok.group(2)
        no = re.search(r'name="([^"]+)"', row)
        if not no:
            continue
        lines = [clean(x) for x in re.findall(r'<div class="line-[^"]*">(.*?)</div>', row, re.S)]
        text = "\n".join(l for l in lines if l)
        arts.append({"no": no.group(1), "chapter": chapter, "text": text,
                     "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                     "url": f"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode={pcode}&flno={no.group(1)}"})
    return {"pcode": pcode, "name": name, "topic": topic, "amended": amended,
            "source": BASE + pcode, "articles": arts}


def main():
    os.makedirs(os.path.join(HERE, "laws"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "changes"), exist_ok=True)
    now = datetime.now(TZ)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    index, changes, errors = [], [], []
    for pcode, topic in LAWS:
        path = os.path.join(HERE, "laws", pcode + ".json")
        old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
        try:
            law = parse(pcode, topic, fetch(pcode))
            if not law["articles"]:
                raise ValueError("解析不到任何條文，頁面格式可能已改變")
        except Exception as e:  # 來源錯誤時保留舊資料，並老實記錄
            errors.append({"pcode": pcode, "error": str(e)})
            if old:
                old["stale"] = True
                index.append({k: old.get(k) for k in ("pcode", "name", "topic", "amended", "source", "fetchedAt")} | {"count": len(old["articles"]), "stale": True})
            continue
        law["fetchedAt"] = stamp
        if old:
            o = {a["no"]: a for a in old["articles"]}
            n = {a["no"]: a for a in law["articles"]}
            for no, a in n.items():
                if no not in o:
                    changes.append({"pcode": pcode, "law": law["name"], "no": no, "type": "新增", "new": a["text"]})
                elif o[no]["hash"] != a["hash"]:
                    changes.append({"pcode": pcode, "law": law["name"], "no": no, "type": "修正", "old": o[no]["text"], "new": a["text"]})
            for no, a in o.items():
                if no not in n:
                    changes.append({"pcode": pcode, "law": law["name"], "no": no, "type": "刪除", "old": a["text"]})
            if old.get("amended") != law["amended"]:
                changes.append({"pcode": pcode, "law": law["name"], "no": "", "type": "修正日期變更", "old": old.get("amended"), "new": law["amended"]})
        json.dump(law, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        index.append({"pcode": pcode, "name": law["name"], "topic": topic, "amended": law["amended"],
                      "source": law["source"], "fetchedAt": stamp, "count": len(law["articles"]), "stale": False})
        time.sleep(1)  # 對官方網站保持禮貌
    json.dump({"syncedAt": stamp, "laws": index, "errors": errors}, open(os.path.join(HERE, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if changes:
        json.dump({"detectedAt": stamp, "changes": changes}, open(os.path.join(HERE, "changes", now.strftime("%Y%m%d-%H%M%S") + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log = os.path.join(HERE, "sync_log.csv")
    new = not os.path.exists(log)
    with open(log, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["同步時間", "成功法規數", "失敗法規數", "條文總數", "偵測到的異動數", "失敗明細"])
        w.writerow([stamp, sum(1 for i in index if not i["stale"]), len(errors), sum(i["count"] for i in index), len(changes), json.dumps(errors, ensure_ascii=False) if errors else ""])
    print(f"{stamp} 法規 {len(index)} 部，條文 {sum(i['count'] for i in index)} 條，異動 {len(changes)} 筆，失敗 {len(errors)} 部")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
