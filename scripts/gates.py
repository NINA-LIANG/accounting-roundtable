#!/usr/bin/env python3
"""機器閘門 G1–G13（docs/05b_測試規劃_草稿.md）。全部通過結束碼 0，否則列出問題並以 1 結束。
用法：python3 scripts/gates.py [--skip-freshness]"""
import csv, glob, json, os, re, sys
from datetime import datetime, timezone, timedelta, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import calc

TZ = timezone(timedelta(hours=8))
BANNED = ["保證", "一定可以節稅", "穩過", "國稅局不會查", "AI 會取代會計", "AI會取代會計", "免費幫你報稅", "私訊幫你看案子"]  # 憲章第七節
WARNING = "依當年度財政部公告為準"
HOTLINE = "0800-000321"
NEEDS_WARNING = re.compile(r"稅率|限額|期限|千分之|百分之|\d+\s*[%％]")
MAX_AGE_DAYS = 7
EXPECTED_LAWS = 30  # docs/02_資料來源清單：SRC-001 到 SRC-030（憲章 v1.1）
REQUIRED_PAGES = ["index.html", "topics.html", "laws.html", "sources.html", "errata.html", "charter.html", "monitor.html", "about.html"]
ERRATA_FIELDS = ["id", "found_at", "article_id", "was", "now", "basis", "found_by", "fixed_at", "published", "new_rule"]
ARTICLE_FIELDS = ["id", "title", "topic", "body", "facts", "citations", "ai_generated", "approved_by", "approved_at", "edit_level", "sync_date"]
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
TW_ID = re.compile(r"(?<![A-Za-z0-9])[A-Z][1289]\d{8}(?!\d)")

def norm(s):
    return re.sub(r"[\s　，。、；：「」『』（）()〔〕.,;:\-－—…]", "", s or "")

def art_no(s):
    """『第 8 條之 1』『8-1』都轉成 '8-1'。"""
    s = str(s).replace(" ", "")
    m = re.search(r"(\d+)(?:條)?(?:之|-)(\d+)", s)
    if m: return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"\d+", s)
    return m.group(0) if m else s

def load_kb(root=ROOT):
    idx = json.load(open(os.path.join(root, "data", "index.json"), encoding="utf8"))
    laws = {}
    for l in idx["laws"]:
        p = os.path.join(root, "data", "laws", l["pcode"] + ".json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf8"))
            laws[d["name"]] = d
    return idx, laws

def load_articles(root=ROOT):
    out = []
    for p in sorted(glob.glob(os.path.join(root, "content", "articles", "*.json"))):
        a = json.load(open(p, encoding="utf8")); a["_path"] = os.path.relpath(p, root); out.append(a)
    return out

def find_article(laws, law, no):
    d = laws.get(law)
    if not d: return None, f"知識庫沒有「{law}」"
    for a in d["articles"]:
        if str(a["no"]) == art_no(no): return a, None
    return None, f"「{law}」沒有第 {no} 條"

# ---- 各道閘門：回傳問題清單，空清單表示通過 ----
def g1_citations(article, laws):
    probs = []
    for c in article.get("citations", []):
        a, err = find_article(laws, c.get("law"), c.get("no"))
        if err: probs.append(err); continue
        for part in re.split(r"…+|\.{3,}", c.get("quote", "")):  # 只允許以省略號截斷，不允許改字
            if norm(part) and norm(part) not in norm(a["text"]):
                probs.append(f"{c['law']}第 {c['no']} 條引文與原文不符：「{part[:20]}」")
        if not norm(c.get("quote", "")): probs.append(f"{c['law']}第 {c['no']} 條沒有引文")
    if not article.get("citations"): probs.append("沒有任何引用")
    return probs

def g2_freshness(idx, today=None):
    now = today or datetime.now(TZ)
    synced = datetime.fromisoformat(idx["syncedAt"].replace("+0800", "+08:00"))
    age = (now - synced).total_seconds() / 86400
    return [f"知識庫距上次同步 {age:.1f} 天，超過 {MAX_AGE_DAYS} 天"] if age > MAX_AGE_DAYS else []

def g3_warning(article):
    b = article.get("body", "")
    return [f"提到稅率、限額或期限，卻沒有「{WARNING}」"] if NEEDS_WARNING.search(b) and WARNING not in b else []

def g4_banned(text):
    return [f"出現禁語「{w}」" for w in BANNED if w in text]

def g5_latest(article):
    return ["標了「最新」卻沒有同步日期"] if "最新" in (article.get("title", "") + article.get("body", "")) and not article.get("sync_date") else []

def g6_fields(article):
    probs = [f"缺少欄位 {f}" for f in ARTICLE_FIELDS if article.get(f) in (None, "", [])]
    if article.get("ai_generated") is not True: probs.append("沒有標示 AI 產出")
    if article.get("edit_level") not in (0, 1, 2, 3): probs.append("修改程度必須是 0–3")
    return probs

def g7_facts(article):
    facts = {(f.get("law"), art_no(f.get("no"))) for f in article.get("facts", [])}
    return [f"引用了事實清單以外的條文：{c.get('law')}第 {c.get('no')} 條"
            for c in article.get("citations", []) if (c.get("law"), art_no(c.get("no"))) not in facts]

def g8_hand_cases():
    probs = []
    if calc.deductible_input_tax([("辦公用品", 500), ("交際應酬", 300), ("酬勞員工個人", 250), ("自用乘人小汽車", 40000)]) != (500, 40550):
        probs.append("手算案例 1（進項稅額扣抵）答案不對")
    if calc.entertainment_limit_sales(50_000_000) != 195_000 or calc.entertainment_limit_sales(50_000_000, blue=True) != 260_000:
        probs.append("手算案例 2（交際費限額）答案不對")
    if calc.retention_until(date(2026, 6, 30)) != (date(2031, 6, 30), date(2036, 6, 30)):
        probs.append("手算案例 3（保存年限）答案不對")
    return probs

def g9_sources(idx, root=ROOT):
    probs = []
    if len(idx["laws"]) != EXPECTED_LAWS: probs.append(f"資料來源應為 {EXPECTED_LAWS} 部法規，目前 {len(idx['laws'])} 部")
    for l in idx["laws"]:
        p = os.path.join(root, "data", "laws", l["pcode"] + ".json")
        if not os.path.exists(p): probs.append(f"缺少法規檔：{l['name']}"); continue
        d = json.load(open(p, encoding="utf8"))
        if not d.get("articles"): probs.append(f"{d['name']} 沒有條文")
        if not d.get("source", "").startswith("https://law.moj.gov.tw/"): probs.append(f"{d['name']} 沒有官方連結")
        if not d.get("amended"): probs.append(f"{d['name']} 沒有修正日期")
    return probs

def g10_article_pages(articles, dist):
    probs = []
    for a in articles:
        p = os.path.join(dist, "articles", a["id"] + ".html")
        if not os.path.exists(p): probs.append(f"{a['id']} 沒有產生文章頁"); continue
        h = open(p, encoding="utf8").read()
        if "核對欄" not in h: probs.append(f"{a['id']} 文章頁沒有核對欄")
        if HOTLINE not in h: probs.append(f"{a['id']} 文章頁沒有個案導向說明（{HOTLINE}）")
    return probs

def g11_errata(root=ROOT):
    probs = []
    for p in sorted(glob.glob(os.path.join(root, "content", "errata", "*.json"))):
        e = json.load(open(p, encoding="utf8"))
        probs += [f"{os.path.basename(p)} 缺少欄位 {f}" for f in ERRATA_FIELDS if e.get(f) in (None, "")]
    return probs

def g12_links(dist):
    probs = [f"缺少頁面 {p}" for p in REQUIRED_PAGES if not os.path.exists(os.path.join(dist, p))]
    for p in glob.glob(os.path.join(dist, "**", "*.html"), recursive=True):
        page = re.sub(r"<script.*?</script>", "", open(p, encoding="utf8").read(), flags=re.S)
        for href in re.findall(r'href="([^"#]+)(?:#[^"]*)?"', page):
            if re.match(r"https?://|mailto:|tel:", href): continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), href))):
                probs.append(f"{os.path.relpath(p, dist)} 的連結打不開：{href}")
    return probs

def g13_secrets(root=ROOT):
    probs = []
    for base in ("content", "site", "scripts", "logs", "docs", ".github"):
        for p in glob.glob(os.path.join(root, base, "**", "*"), recursive=True):
            if not os.path.isfile(p) or p.endswith((".png", ".jpg")): continue
            t = open(p, encoding="utf8", errors="ignore").read()
            if SECRET.search(t): probs.append(f"{os.path.relpath(p, root)} 疑似含有金鑰")
            if base in ("content", "logs") and TW_ID.search(t): probs.append(f"{os.path.relpath(p, root)} 疑似含有身分證字號格式")
    return probs

def run_all(root=ROOT, dist=None, skip_freshness=False):
    dist = dist or os.path.join(root, "dist")
    idx, laws = load_kb(root); arts = load_articles(root)
    res = {f"G{i}": [] for i in range(1, 14)}
    for a in arts:
        tag = lambda ps: [f"{a['_path']}：{p}" for p in ps]
        res["G1"] += tag(g1_citations(a, laws)); res["G3"] += tag(g3_warning(a))
        res["G4"] += tag(g4_banned(a.get("title", "") + a.get("body", ""))); res["G5"] += tag(g5_latest(a))
        res["G6"] += tag(g6_fields(a)); res["G7"] += tag(g7_facts(a))
    if not skip_freshness: res["G2"] = g2_freshness(idx)
    for p in glob.glob(os.path.join(dist, "**", "*.html"), recursive=True):
        if os.path.basename(p) == "charter.html": continue  # 憲章頁本身要列出禁語清單
        text = re.sub(r"<[^>]+>", "", open(p, encoding="utf8").read())
        res["G4"] += [f"{os.path.relpath(p, dist)}：{x}" for x in g4_banned(text)]
    res["G8"] = g8_hand_cases(); res["G9"] = g9_sources(idx, root)
    res["G10"] = g10_article_pages(arts, dist); res["G11"] = g11_errata(root)
    res["G12"] = g12_links(dist); res["G13"] = g13_secrets(root)
    return res

NAMES = {"G1": "引用比對", "G2": "知識庫 7 天內同步", "G3": "稅率限額期限警語", "G4": "禁語", "G5": "「最新」附同步日期", "G6": "核准與透明標示",
         "G7": "只用事實清單", "G8": "三個手算案例", "G9": "資料來源齊全", "G10": "文章頁核對欄", "G11": "勘誤欄位", "G12": "頁面與連結", "G13": "金鑰與個資"}

if __name__ == "__main__":
    res = run_all(skip_freshness="--skip-freshness" in sys.argv)
    bad = 0
    for g, probs in res.items():
        print(f"{'通過' if not probs else '沒過'}　{g} {NAMES[g]}")
        for p in probs: print("　　－", p); bad += 1
    sys.exit(1 if bad else 0)
