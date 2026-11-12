"""三個手算案例的計算規則（docs/02b_資料字典與手算案例.md）。金額單位：元。"""
from datetime import date

# 營業稅法第 19 條第 1 項：不得扣抵的進項稅額類別
NON_DEDUCTIBLE = {"無合規憑證": 1, "非供本業及附屬業務使用": 2, "交際應酬": 3, "酬勞員工個人": 4, "自用乘人小汽車": 5}

def deductible_input_tax(items):
    """items: [(用途, 進項稅額)]；回傳 (可扣抵, 不可扣抵)。"""
    ok = sum(t for kind, t in items if kind not in NON_DEDUCTIBLE)
    no = sum(t for kind, t in items if kind in NON_DEDUCTIBLE)
    return ok, no

# 所得稅法第 37 條第 1 項第 2 款、查核準則第 80 條第 1 款第 2 目：銷貨部分，(級距上限, 普通千分比, 藍色千分比)
SALES_BRACKETS = [(30_000_000, 4.5, 6), (150_000_000, 3, 4), (600_000_000, 2, 3), (None, 1, 1.5)]

def entertainment_limit_sales(net_sales, blue=False):
    """以銷貨為目的之交際費限額。blue=True 表示藍色申報或會計師簽證。"""
    limit, low = 0.0, 0
    for top, normal, blue_rate in SALES_BRACKETS:
        rate = blue_rate if blue else normal
        hi = net_sales if top is None else min(net_sales, top)
        if hi > low:
            limit += (hi - low) * rate / 1000
        if top is None or net_sales <= top:
            break
        low = top
    return round(limit)

def retention_until(closing_done: date):
    """商業會計法第 38 條：憑證至少 5 年、帳簿與財務報表至少 10 年（自年度決算程序辦理終了後起算）。"""
    return (closing_done.replace(year=closing_done.year + 5), closing_done.replace(year=closing_done.year + 10))
