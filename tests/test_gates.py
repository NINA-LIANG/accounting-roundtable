"""每道閘門都有一個「正常會過」與一個「故意弄壞會被擋下」的測試（docs/05b_測試規劃_草稿.md）。"""
import copy, json, os, shutil, sys
from datetime import datetime, timedelta, date
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gates, calc, build

@pytest.fixture(scope="module")
def kb(): return gates.load_kb()
@pytest.fixture
def good(): return json.load(open(os.path.join(ROOT, "tests", "fixtures", "good_article.json"), encoding="utf8"))

@pytest.fixture
def site(tmp_path, good):
    """複製一份 repository、放進範例文章並產生網站，回傳 (根目錄, dist)。"""
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__", ".pytest_cache"))
    json.dump(good, open(root / "content" / "articles" / "T-0001.json", "w", encoding="utf8"), ensure_ascii=False)
    build.ROOT, build.DIST = str(root), str(root / "dist"); build.build()
    yield str(root), str(root / "dist")
    build.ROOT, build.DIST = ROOT, os.path.join(ROOT, "dist")

def test_good_article_passes_everything(site):
    root, dist = site
    assert {g: p for g, p in gates.run_all(root, dist, skip_freshness=True).items() if p} == {}

def test_g1_changed_wording_is_blocked(kb, good):
    assert gates.g1_citations(good, kb[1]) == []
    bad = copy.deepcopy(good); bad["citations"][0]["quote"] = "交際應酬用之貨物或勞務，得扣抵銷項稅額"
    assert gates.g1_citations(bad, kb[1])
def test_g1_fifteen_days_changed_to_twenty_is_blocked(kb):
    law, text = next((n, a) for n, d in kb[1].items() for a in d["articles"] if "十五日內" in a["text"])
    i = text["text"].index("十五日內"); quote = text["text"][max(0, i - 8):i + 4]
    mk = lambda q: {"citations": [{"law": law, "no": text["no"], "quote": q}]}
    assert gates.g1_citations(mk(quote), kb[1]) == []
    assert gates.g1_citations(mk(quote.replace("十五日內", "二十日內")), kb[1])
def test_g1_nonexistent_article_is_blocked(kb, good):
    bad = copy.deepcopy(good); bad["citations"][0]["no"] = "999"
    assert gates.g1_citations(bad, kb[1])

def test_g2_eight_days_old_is_blocked(kb):
    synced = datetime.fromisoformat(kb[0]["syncedAt"].replace("+0800", "+08:00"))
    assert gates.g2_freshness(kb[0], synced + timedelta(days=6)) == []
    assert gates.g2_freshness(kb[0], synced + timedelta(days=8))

def test_g3_missing_warning_is_blocked(good):
    a = copy.deepcopy(good); a["body"] += "\n交際費限額是銷貨淨額的千分之四點五。"
    assert gates.g3_warning(a)
    a["body"] += "稅率、限額與期限" + "依當年度財政部公告為準。"
    assert gates.g3_warning(a) == []

def test_g4_banned_phrase_is_blocked(good):
    assert gates.g4_banned(good["body"]) == []
    assert gates.g4_banned(good["body"] + "照這樣做一定可以節稅")

def test_g5_latest_without_sync_date_is_blocked(good):
    a = copy.deepcopy(good); a["title"] = "最新規定：" + a["title"]
    assert gates.g5_latest(a) == []
    a["sync_date"] = ""
    assert gates.g5_latest(a)

def test_g6_missing_approval_is_blocked(good):
    assert gates.g6_fields(good) == []
    a = copy.deepcopy(good); a["approved_at"] = ""
    assert gates.g6_fields(a)
    b = copy.deepcopy(good); b["ai_generated"] = False
    assert gates.g6_fields(b)

def test_g7_citation_outside_fact_list_is_blocked(good):
    assert gates.g7_facts(good) == []
    a = copy.deepcopy(good); a["citations"].append({"law": "所得稅法", "no": "37", "quote": "業務上直接支付之交際應酬費用"})
    assert gates.g7_facts(a)

def test_g8_hand_cases():
    assert gates.g8_hand_cases() == []
    assert calc.deductible_input_tax([("辦公用品", 500), ("交際應酬", 300), ("酬勞員工個人", 250), ("自用乘人小汽車", 40000)]) == (500, 40550)
    assert calc.entertainment_limit_sales(50_000_000) == 195_000
    assert calc.entertainment_limit_sales(50_000_000, blue=True) == 260_000
    assert calc.entertainment_limit_sales(30_000_000) == 135_000
    assert calc.retention_until(date(2026, 6, 30)) == (date(2031, 6, 30), date(2036, 6, 30))
def test_g8_wrong_bracket_rate_is_blocked(monkeypatch):
    monkeypatch.setattr(calc, "SALES_BRACKETS", [(30_000_000, 4.5, 6), (150_000_000, 4, 4), (600_000_000, 2, 3), (None, 1, 1.5)])
    assert gates.g8_hand_cases()

def test_g9_missing_law_file_is_blocked(site, kb):
    root, _ = site
    assert gates.g9_sources(kb[0], root) == []
    os.remove(os.path.join(root, "data", "laws", "G0380028.json"))
    assert gates.g9_sources(kb[0], root)

def test_g10_missing_check_panel_is_blocked(site, good):
    _, dist = site
    assert gates.g10_article_pages([good], dist) == []
    p = os.path.join(dist, "articles", "T-0001.html"); h = open(p, encoding="utf8").read()
    open(p, "w", encoding="utf8").write(h.replace("核對欄", ""))
    assert gates.g10_article_pages([good], dist)

def test_g11_incomplete_erratum_is_blocked(site):
    root, _ = site
    e = {"id": "ERR-001", "found_at": "2026-11-12", "article_id": "T-0001", "was": "原文", "now": "", "basis": "SRC-001 第 19 條",
         "found_by": "本人", "fixed_at": "2026-11-12", "published": "否", "new_rule": "新增規則"}
    json.dump(e, open(os.path.join(root, "content", "errata", "ERR-001.json"), "w", encoding="utf8"), ensure_ascii=False)
    assert gates.g11_errata(root)

def test_g12_renamed_page_is_blocked(site):
    _, dist = site
    assert gates.g12_links(dist) == []
    os.rename(os.path.join(dist, "charter.html"), os.path.join(dist, "charter2.html"))
    assert gates.g12_links(dist)

def test_g13_planted_key_is_blocked(site):
    root, _ = site
    assert gates.g13_secrets(root) == []
    open(os.path.join(root, "content", "note.txt"), "w").write("key = " + "sk-ant-" + "x" * 30)
    assert gates.g13_secrets(root)
