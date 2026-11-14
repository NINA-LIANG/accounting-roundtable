#!/usr/bin/env python3
"""把 docs/、data/、content/、logs/ 產生成靜態網站 dist/。只用 Python 標準函式庫。"""
import csv, glob, html, json, os, re, shutil, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
E = html.escape
NAV = [("index.html", "首頁"), ("topics.html", "實務問題"), ("laws.html", "法規知識庫"), ("sources.html", "資料來源與同步紀錄"), ("errata.html", "勘誤"),
       ("monitor.html", "工作日誌與監控"), ("charter.html", "憲章"), ("about.html", "關於")]
WARN = "依當年度財政部公告為準"

def page(path, title, body, depth=0):
    up = "../" * depth
    nav = "".join(f'<a href="{up}{h}"{" aria-current=\"page\"" if h == path else ""}>{t}</a>' for h, t in NAV)
    out = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}｜會計圓桌</title><link rel="stylesheet" href="{up}style.css"></head><body>
<header class="top"><div class="wrap"><a class="brand" href="{up}index.html">✨ 會計圓桌</a><nav>{nav}</nav></div></header>
<div class="wrap"><main>{body}</main></div>
<footer><div class="wrap"><div>🐾 本站內容為一般性說明，不是報稅代辦，不回答個別案件，也不等同專業意見。個案請洽會計師、記帳士，或國稅局免費服務專線 0800-000321。</div></div></footer>
</body></html>'''
    full = os.path.join(DIST, path); os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf8").write(out)

def inline(s):
    s = E(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return re.sub(r"(?<![\"=>])(https?://[^\s<）)]+)", r'<a href="\1">\1</a>', s)

def md(text):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            out.append('<div class="tw"><table>' + "".join("<tr>" + "".join(f"<{'th' if n == 0 else 'td'}>{inline(c)}</{'th' if n == 0 else 'td'}>" for c in r) + "</tr>" for n, r in enumerate(rows)) + "</table></div>")
            continue
        m = re.match(r"(#{1,3}) (.*)", l)
        if m: out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"(\d+\.|-) ", l):
            tag = "ol" if l[0].isdigit() else "ul"; items = []
            while i < len(lines) and re.match(r"\s*(\d+\.|-) ", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\s*(\d+\.|-) ', '', lines[i]))}</li>"); i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>"); continue
        elif l.startswith(">"): out.append(f"<blockquote>{inline(l.lstrip('> '))}</blockquote>")
        elif l.strip(): out.append(f"<p>{inline(l)}</p>")
        i += 1
    return "\n".join(out)

def read_csv(p):
    return list(csv.reader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []

def table(rows, limit=None):
    if not rows: return '<p class="mut">目前沒有紀錄。</p>'
    head, body = rows[0], rows[1:]
    if limit: body = body[-limit:][::-1]
    return '<div class="tw"><table><tr>' + "".join(f"<th>{E(c)}</th>" for c in head) + "</tr>" + "".join("<tr>" + "".join(f"<td>{E(c)}</td>" for c in r) + "</tr>" for r in body) + "</table></div>"

def law_url(laws, law, no):
    d = laws.get(law)
    for a in (d or {}).get("articles", []):
        if str(a["no"]) == str(no): return a["url"]
    return (d or {}).get("source", "#")

def build():
    shutil.rmtree(DIST, ignore_errors=True); os.makedirs(DIST)
    shutil.copy(os.path.join(ROOT, "site", "style.css"), DIST)
    shutil.copytree(os.path.join(ROOT, "data", "laws"), os.path.join(DIST, "data", "laws"))
    shutil.copy(os.path.join(ROOT, "data", "index.json"), os.path.join(DIST, "data"))
    idx = json.load(open(os.path.join(ROOT, "data", "index.json"), encoding="utf8"))
    laws = {}
    for l in idx["laws"]:
        d = json.load(open(os.path.join(ROOT, "data", "laws", l["pcode"] + ".json"), encoding="utf8")); laws[d["name"]] = d
    synced = idx["syncedAt"][:10]; total = sum(len(d["articles"]) for d in laws.values())
    arts = []
    for p in sorted(glob.glob(os.path.join(ROOT, "content", "articles", "*.json")), reverse=True):
        a = json.load(open(p, encoding="utf8"))
        if a.get("approved_at") == "以合併日為準":  # 本人以合併 Pull Request 核准；日期取該檔最後一次進入 main 的提交日
            try:
                d = subprocess.run(["git", "log", "-1", "--format=%cs", "--", p], cwd=ROOT, capture_output=True, text=True).stdout.strip()
            except OSError:
                d = ""
            a["approved_at"] = d or "合併後產生"
        arts.append(a)

    # 首頁（風格 D 馬卡龍療癒風：扭蛋抽一篇、分類頁籤、拍立得卡片、愛心投票、人氣排行）
    GROUPS = [("vat", "發票營業稅 🧾", {"營業稅", "憑證"}, "🧾"), ("tax", "所得稅扣繳 💰", {"所得稅", "稅務"}, "💰"),
              ("pay", "薪資勞健保 🍙", {"勞保", "薪資"}, "🍙"), ("book", "帳務結帳 📒", {"帳務", "結帳", "成本"}, "📒")]
    def grp(t):
        for k, _, ts, ic in GROUPS:
            if t in ts: return k, ic
        return "book", "📒"
    cards, data = [], []
    for a in arts:
        k, ic = grp(a["topic"]); c0 = a["citations"][0]
        cards.append(f'''<article class="card c-{k}" data-id="{E(a["id"])}" data-g="{k}"><div class="photo" aria-hidden="true">{ic}</div>
<div class="meta"><span class="pill">{E(a["topic"])}</span><span>核准 {E(a["approved_at"])}</span></div>
<h3><a href="articles/{E(a["id"])}.html">{E(a["title"])}</a></h3><p class="mut" style="font-size:.84rem">📌 {E(c0["law"])}第 {E(str(c0["no"]))} 條</p>
<div class="row"><button class="btn vote" type="button" data-id="{E(a["id"])}">❤ 實用一票</button><span class="count" data-c="{E(a["id"])}">0 票</span></div></article>''')
        data.append({"id": a["id"], "t": a["title"], "g": k, "topic": a["topic"]})
    tabs = '<button class="btn tab" type="button" data-g="all" aria-pressed="true">全部 📚</button>' + "".join(f'<button class="btn tab" type="button" data-g="{k}" aria-pressed="false">{E(n)}</button>' for k, n, _, _ in GROUPS)
    grid = "".join(cards) or '<p class="mut">目前還沒有已核准的文章。每一篇都要通過機器閘門並由本人核准後才會出現在這裡。</p>'
    page("index.html", "首頁", f'''<section class="panel hero"><h1>✨ 會計圓桌 ✨</h1>
<p>寫給想用 AI 把會計工作做得更快的你 🐾</p>
<p style="max-width:34em">想用 AI 又怕出錯？每篇我們都會跟你說：哪一步放心交給 AI、哪一步一定要自己看，法條原文也幫你附好了。</p>
<p class="mut" style="font-size:.9rem">每一句稅法說法都點得回原文 · 知識庫 {len(laws)} 部法規、{total:,} 條 · 同步日 {synced}</p>
<button class="btn" type="button" id="gacha">🎲 今天學什麼？（隨機抽籤扭蛋）</button></section>
<div class="tabs" role="group" aria-label="文章分類">{tabs}</div>
<div class="layout"><div class="grid" id="grid">{grid}</div>
<aside class="panel rank" aria-labelledby="rk"><h2 id="rk">👑 人氣排行</h2><ol id="top"></ol>
<p class="mut" style="font-size:.8rem">票數只存在你這台裝置的瀏覽器，不會上傳，也不代表其他讀者。</p></aside></div>
<dialog id="dlg"><div class="bubble"><div class="mascot" aria-hidden="true">🐰</div><p class="say" id="say"></p><p><strong id="pick"></strong></p>
<div class="actions"><a class="btn go" id="go" href="#">去看這篇 ✨</a><button class="btn again" type="button" id="again">再抽一次 🎲</button><button class="btn close" type="button" id="close">先不要</button></div></div></dialog>
<div class="toast" id="toast" role="status"></div>
<script>
const ARTS={json.dumps(data, ensure_ascii=False)};
const LINES={{vat:["發票的事搞懂了，報營業稅就不慌 🧾","打統編之前先想想這篇 ✨","今天就把作廢和折讓分清楚吧 🍰"],tax:["所得稅的細節，今天補一點 💰","申報季前先複習，心裡比較踏實 🍵","數字算清楚，主管問了也不怕 👑"],pay:["薪資和勞健保，員工最在意的事 🍙","每月核對一次，少一點加班 💖","今天幫同事把錢算對吧 🐾"],book:["帳記得真實，報表才看得懂 📒","月結前先看這篇，結帳更順 ✨","這題 FP&A 也天天用得到 🍵"]}};
const KEY='roundtable-votes';let V={{}};try{{V=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
const save=()=>{{try{{localStorage.setItem(KEY,JSON.stringify(V))}}catch(e){{}}}};
const $=s=>document.querySelector(s),esc=s=>s.replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
function counts(){{document.querySelectorAll('[data-c]').forEach(e=>e.textContent=(V[e.dataset.c]||0)+' 票')}}
function rank(){{const m=['👑','🥇','🥈','🥉'];const r=ARTS.filter(a=>V[a.id]).sort((a,b)=>V[b.id]-V[a.id]).slice(0,3);
 $('#top').innerHTML=r.length?r.map((a,i)=>'<li><span class="medal">'+m[i+1]+'</span><span><a href="articles/'+a.id+'.html">'+esc(a.t)+'</a><br><span class="count">'+V[a.id]+' 票</span></span></li>').join(''):'<li><span class="medal">'+m[0]+'</span><span>還沒有人投票，幫最實用的那篇投下第一票吧！</span></li>'}}
function toast(t){{const e=$('#toast');e.textContent=t;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),1400)}}
function hearts(x,y){{for(let i=0;i<6;i++){{const h=document.createElement('span');h.className='heart';h.textContent=['💖','✨','❤'][i%3];h.style.left=(x-10+Math.random()*30)+'px';h.style.top=(y-10)+'px';h.style.setProperty('--dx',(Math.random()*80-40)+'px');h.style.animationDelay=(i*60)+'ms';document.body.appendChild(h);setTimeout(()=>h.remove(),1400)}}}}
document.querySelectorAll('.vote').forEach(b=>b.addEventListener('click',e=>{{const id=b.dataset.id;V[id]=(V[id]||0)+1;save();counts();rank();
 b.classList.remove('pop');void b.offsetWidth;b.classList.add('pop');const r=b.getBoundingClientRect();hearts(r.left+r.width/2,r.top);toast('投票成功！🎉')}}));
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{{document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-pressed',x===t));
 document.querySelectorAll('.card').forEach(c=>c.hidden=!(t.dataset.g==='all'||c.dataset.g===t.dataset.g))}}));
function draw(){{if(!ARTS.length)return;const a=ARTS[Math.floor(Math.random()*ARTS.length)],l=LINES[a.g];$('#say').textContent=l[Math.floor(Math.random()*l.length)];$('#pick').textContent=a.t;$('#go').href='articles/'+a.id+'.html'}}
$('#gacha').addEventListener('click',()=>{{draw();$('#dlg').showModal()}});$('#again').addEventListener('click',draw);$('#close').addEventListener('click',()=>$('#dlg').close());
counts();rank();
</script>''')

    # 文章頁
    for a in arts:
        paras = "".join("<p>" + re.sub(r"^(場景|AI 可以幫什麼|自己要核對|為什麼|法條|不做會怎樣|小提醒)：", r"<strong>\1</strong>：", inline(p)) + "</p>" for p in a["body"].split("\n") if p.strip())
        cites = "".join(f'<div class="cite"><a href="{E(law_url(laws, c["law"], c["no"]))}">{E(c["law"])}第 {E(str(c["no"]))} 條</a>：「{E(c["quote"])}」</div>' for c in a["citations"])
        rows = "".join(f'<tr><td>{E(c["law"])}</td><td>第 {E(str(c["no"]))} 條</td></tr>' for c in a["citations"])
        page(f'articles/{a["id"]}.html', a["title"], f'''<div class="meta"><span>{E(a["topic"])}</span><span>同步日 {E(a["sync_date"])}</span></div>
<h1>{E(a["title"])}</h1><div class="meta"><span class="pill">AI 產出</span><span class="pill">本人已核對</span><span class="pill">修改程度 {a["edit_level"]}</span></div>
{paras}<h2>法規出處</h2><div class="list">{cites}</div>
<div class="panel"><h2>核對欄</h2><div class="tw"><table><tr><th>核對者</th><td>{E(a["approved_by"])}</td></tr><tr><th>核對日期</th><td>{E(a["approved_at"])}</td></tr><tr><th>知識庫同步日期</th><td>{E(a["sync_date"])}</td></tr></table></div>
<h3>本篇引用條文</h3><div class="tw"><table><tr><th>法規</th><th>條號</th></tr>{rows}</table></div>
<p class="mut">稅率、限額、期限一律{WARN}。本站不回答個別案件，個案請洽會計師、記帳士，或國稅局免費服務專線 0800-000321。</p></div>''', depth=1)

    # 法規知識庫（瀏覽器端搜尋）
    page("laws.html", "法規知識庫", f'''<h1>法規知識庫</h1><p class="mut">條文原文取自全國法規資料庫，一字不改。同步日 {synced}。</p>
<label for="q" class="mut">輸入關鍵字，例如「交際」「進項稅額」「保存」</label><input type="search" id="q" autocomplete="off">
<p id="count" class="mono mut"></p><div id="out" class="list"></div>
<script>
const out=document.getElementById('out'),cnt=document.getElementById('count'),q=document.getElementById('q');let all=[];
const esc=s=>s.replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
fetch('data/index.json').then(r=>r.json()).then(i=>Promise.all(i.laws.map(l=>fetch('data/laws/'+l.pcode+'.json').then(r=>r.json())))).then(ls=>{{
 ls.forEach(d=>d.articles.forEach(a=>all.push({{law:d.name,amended:d.amended,no:a.no,text:a.text,url:a.url}})));cnt.textContent='已載入 '+all.length+' 條';render();
}}).catch(()=>{{cnt.textContent='法規資料載入失敗，請重新整理。'}});
function render(){{const k=q.value.trim();if(!k){{out.innerHTML='';return}}
 const hit=all.filter(a=>a.text.includes(k)||a.law.includes(k));cnt.textContent='找到 '+hit.length+' 條'+(hit.length>50?'，顯示前 50 條':'');
 out.innerHTML=hit.slice(0,50).map(a=>'<div class="panel"><div class="meta"><span>'+esc(a.law)+'</span><span>修正 '+esc(a.amended)+'</span></div><h3><a href="'+a.url+'">第 '+esc(String(a.no))+' 條</a></h3><p>'+esc(a.text).replace(/\\n/g,'<br>')+'</p></div>').join('')||'<p class="mut">找不到，換個關鍵字試試。</p>';}}
q.addEventListener('input',render);
</script>''')

    # 實務問題前 20 名（選題池）：只放題目與排名，不放法規解讀；解讀要寫成文章、過閘門並經本人核准
    tp = json.load(open(os.path.join(ROOT, "data", "topics.json"), encoding="utf8"))
    done = {a["id"]: a["title"] for a in arts}
    trs = "".join(f'<tr><td>{t["rank"]}</td><td>{E(t["question"])}</td><td>{E(t["category"])}</td><td>{t["freq"]}</td><td>{t["official"]}</td><td>{t["impact"]}</td><td>{t["score"]}</td><td>' +
                  (f'<a href="articles/{E(t["article_id"])}.html">已有文章</a>' if t.get("article_id") in done else '<span class="mut">尚未寫成文章</span>') + "</td></tr>" for t in tp["topics"])
    page("topics.html", "實務問題", f'''<h1>會計人實務問題前 20 名</h1>
<p>這是會計圓桌的選題池：台灣會計人在論壇、社群與官方宣導裡最常遇到的 20 個實務問題。每一題之後會寫成附法規出處的文章，經本人核准後才會上線。</p>
<div class="tw"><table><tr><th>名次</th><th>問題</th><th>類別</th><th>討論頻度</th><th>官方點名</th><th>出錯後果</th><th>總分</th><th>文章</th></tr>{trs}</table></div>
<h2>怎麼排名的</h2><p>以關鍵字搜尋 PTT、Dcard、Mobile01、Threads、事務所部落格與財政部、國稅局、健保署宣導頁，約 20 組搜尋、200 筆結果。每題依討論頻度、官方點名、出錯後果各給 1 到 3 分，滿分 9 分。整理日期 {E(tp["compiledAt"])}。</p>
<p class="mut">限制：這是有依據的估計排名，不是統計抽樣。許多論壇文章是 2015 到 2023 年的舊文，搜尋引擎的排序也會影響看到哪些文章。</p>''')

    # 資料來源與同步紀錄
    src = [["編號", "法規", "最新修正日期", "條數", "官方連結"]] + [[f"SRC-{n:03d}", l["name"], l["amended"], str(l["count"]), l["source"]] for n, l in enumerate(idx["laws"], 1)]
    src_html = '<div class="tw"><table><tr>' + "".join(f"<th>{c}</th>" for c in src[0]) + "</tr>" + "".join(f'<tr><td class="mono">{r[0]}</td><td>{E(r[1])}</td><td>{E(r[2])}</td><td>{r[3]}</td><td><a href="{E(r[4])}">全國法規資料庫</a></td></tr>' for r in src[1:]) + "</table></div>"
    changes = sorted(glob.glob(os.path.join(ROOT, "data", "changes", "*.json")))
    ch_html = "".join(f"<li>{E(os.path.basename(p))}：{len(json.load(open(p, encoding='utf8')).get('changes', []))} 筆異動</li>" for p in changes[-20:])
    page("sources.html", "資料來源與同步紀錄", f'''<h1>資料來源與同步紀錄</h1><p>知識庫只收錄下列官方來源，最後同步於 {E(idx["syncedAt"])}。尚未收錄財政部解釋函令；IFRS 與企業會計準則公報只放編號、摘要與官方連結。</p>
<h2>資料來源</h2>{src_html}<h2>同步紀錄（最近 30 次）</h2>{table(read_csv(os.path.join(ROOT, "data", "sync_log.csv")), 30)}
<h2>抽查比對紀錄（最近 30 次）</h2>{table(read_csv(os.path.join(ROOT, "data", "verify_log.csv")), 30)}
<h2>法規異動</h2>{"<ul>" + ch_html + "</ul>" if ch_html else '<p class="mut">開始同步以來尚未偵測到條文異動。</p>'}''')

    # 勘誤
    errs = [json.load(open(p, encoding="utf8")) for p in sorted(glob.glob(os.path.join(ROOT, "content", "errata", "*.json")))]
    er = "".join(f'<div class="panel"><div class="meta"><span>{E(e["id"])}</span><span>更正日 {E(e["fixed_at"])}</span></div><p>原本：{E(e["was"])}</p><p>更正：{E(e["now"])}</p><p class="mut">依據：{E(e["basis"])}</p><p class="mut">因此新增的防護規則：{E(e["new_rule"])}</p></div>' for e in errs)
    page("errata.html", "勘誤", f'<h1>勘誤</h1><p class="mut">每一筆更正都會留在這裡，並寫明因此新增了哪一條防護規則。</p><div class="list">{er or "<p>目前沒有勘誤。</p>"}</div>')

    # 工作日誌與監控
    days = sorted(glob.glob(os.path.join(ROOT, "logs", "daily", "*.md")), reverse=True)
    logs = "".join(f'<details class="panel"><summary>{E(os.path.basename(p)[:-3])}</summary>{md(open(p, encoding="utf8").read())}</details>' for p in days[:30])
    page("monitor.html", "工作日誌與監控", f'''<h1>工作日誌與監控</h1><p class="mut">每天檢查七位 AI 員工該做的事有沒有做、資料有沒有確實更新。檢查是程式規則，不由 AI 判斷。</p>
<h2>監控總表（最近 30 天）</h2>{table(read_csv(os.path.join(ROOT, "logs", "監控總表.csv")), 30)}<h2>每日工作日誌</h2><div class="list">{logs or '<p class="mut">還沒有工作日誌。</p>'}</div>''')

    # 憲章、關於
    page("charter.html", "憲章", md(open(os.path.join(ROOT, "docs", "01_憲章_題目單.md"), encoding="utf8").read()))
    roles = [("研究員", "從法規異動與實務痛點找題目，先交事實清單"), ("文案寫手", "把條文寫成白話，每個說法附條號與引文"), ("腳本寫手", "改寫成輪播與短影音腳本"),
             ("設計師", "圖卡文字稿與版面"), ("發布員", "整理各平台發布包，不自行發布"), ("數據分析師", "整理成效並回饋下一輪題目"), ("內容經理", "檢查每道關卡與每日工作是否完成")]
    page("about.html", "關於", f'''<h1>關於會計圓桌</h1><p>這個站由一個人經營。內容由七位 AI 員工協作產出，法規說法只取自官方條文，並由程式逐字比對；每一篇發布前都由本人核准。</p>
<h2>七位 AI 員工</h2><div class="tw"><table><tr><th>角色</th><th>負責什麼</th></tr>{"".join(f"<tr><td>{r}</td><td>{d}</td></tr>" for r, d in roles)}</table></div>
<h2>作者</h2><p class="mut">作者介紹由本人撰寫，尚未提供。</p>''')
    print("已產生", len(glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True)), "個頁面")

if __name__ == "__main__":
    build()
