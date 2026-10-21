"""Shapes and values of real BSE responses captured on 12 Oct 2026 (ABB India, scrip 500002), used to test
the tools without touching BSE. Values are abridged; keep the shapes faithful when editing."""
import json
def mk(i, d, v, h='0'):
    return {"type": "Type1_Sh3_IND_AS", "Fld_SequenceID": "0", "fld_type": f"{i}.0000", "fld_desc": d, "Value": f"{v}", "Header": h}

LINES = ["Net Sales/Revenue From Operations", "Other Income", "Total Income", "Expenditure",
         "Changes in inventories of finished goods, work-in-progress and stock-in-trade", "Cost of Materials Consumed",
         "Depreciation and amortisation expense", "Employee benefit expense", "Finance Costs", "Other Expenses",
         "Purchases of stock-in-trade", "Profit after Interest but before Exceptional Items",
         "Profit (+)/ Loss (-) from Ordinary Activities before Tax", "Tax", "Current tax", "Deferred tax",
         "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax", "Net Profit", "Basic EPS for continuing operation",
         "Basic for discontinued & continuing operation", "Diluted EPS for continuing operation", "Diluted for discontinued & continuing operation"]
Q = {  # values observed from Corp_detailedResult_Transpose_ng
    "130.00": ("Un-Audited", "01-Apr-26", "30-Jun-26", [35588.7, 926.7, 36515.4, -31527.7, 50.8, -17574.7, -392.3, -2509.7, -17.1, -7394.5, -3690.2, 4987.7, 4987.7, -1287.0, -1467.0, 180.0, 3700.7, 3623.0, 17.46, -0.37, 17.46, -0.37]),
    "129.00": ("Un-Audited", "01-Jan-26", "31-Mar-26", [31840.6, 996.4, 32837.0, -28218.3, 515.4, -16442.2, -423.6, -2528.6, -38.1, -6888.2, -2413.0, 4618.7, 4618.7, -1199.6, -1226.5, 26.9, 3419.1, 17836.5, 16.14, 68.04, 16.14, 68.04]),
    # 128 and 127 as BSE returned them live on 19 Oct 2026 through the bse tools
    "128.00": ("Audited", "01-Oct-25", "31-Dec-25", [35570.1, 763.3, 36333.4, -30557.5, -1516.5, -16466.3, -396.4, -2913.7, -53.5, -6496.4, -2714.7, 5775.9, 5775.9, -1432.7, -1362.8, -69.9, 4343.2, 4328.5, 20.5, -0.07, 20.5, -0.07]),
    "127.00": ("Un-Audited", "01-Jul-25", "30-Sep-25", [33107.2, 839.5, 33946.7, -28525.6, 342.9, -17559.7, -365.9, -2222.5, -56.4, -6261.4, -2402.6, 5421.1, 5421.1, -1332.3, -1232.4, -99.9, 4088.8, 4090.4, 19.3, 0.01, 19.3, 0.01]),
    "126.00": ("Un-Audited", "01-Apr-25", "30-Jun-25", [31754.4, 997.5, 32751.9, -28010.8, 1479.1, -16598.3, -355.4, -2160.0, -41.9, -6989.5, -3344.8, 4741.1, 4741.1, -1220.3, -1088.0, -132.3, 3520.8, 3517.4, 16.62, -0.02, 16.62, -0.02]),
}
ANN = [{"SCRIP_CD": 500002, "SLONGNAME": "ABB India Ltd", "NEWS_DT": f"2026-10-{10-i:02d}T10:00:00", "HEADLINE": h_, "CATEGORYNAME": c_, "SUBCATNAME": c_,
        "ATTACHMENTNAME": a_} for i, (h_, c_, a_) in enumerate([
    ("<img src=x onerror=window.__pwned=1>Closure of Trading Window", "Company Update", "w1.pdf"),
    ("State Bank of India has informed BSE about : <BR><BR>1. Standalone Financial Results for the period ended December 31, 2025<BR><BR>2. Consolidated &amp; more", "Result", "res1.pdf"),
    ("Change in Management", "Company Update", ""),
    ("Newspaper Publication", "Company Update", "w4.pdf"),
    ("Financial results Q1", "Result", "res2.pdf"),
    ("Analyst call intimation", "Company Update", "w6.pdf"),
    ("Annual report", "AGM/EGM", "w7.pdf")])]
# A quarter that isn't filed yet: BSE answers with the meta rows only, all empty (seen live for 131.00 on
# 19 Oct 2026). It must count as "not filed", not as a quarter with no numbers.
PLACEHOLDER = {"131.00"}


def detail(q):
    if q in PLACEHOLDER:
        return {"table1": [mk(0, "Type", "", "2"), mk(0, "Date Begin", "", "2"), mk(0, "Date End", "", "2")]}
    if q not in Q:
        return {"table1": []}
    typ, b, e, vals = Q[q]
    meta = [mk(0, "Type", typ, "2"), mk(0, "Date Begin", b, "2"), mk(0, "Date End", e, "2")]
    return {"table1": meta + [mk(i + 1, d, f"{v:.4f}", "1" if d == "Expenditure" else "0") for i, (d, v) in enumerate(zip(LINES, vals))]}

pts = []
for i in range(30):
    mm = 540 + i * 5
    pts.append({"dttm": f"Mon Oct 12 2026 {mm // 60:02d}:{mm % 60:02d}:44", ("vale0" if i == 0 else "vale1"): f"{6950 + (i % 7) * 4 + i:.2f}", "vole": "0"})

# StockReachGraphCas with flag=12M: one point per trading day, in the format seen live (ABB, Oct 2026).
HIST = []
_day = __import__("datetime").date(2025, 10, 21)
while len(HIST) < 250:
    if _day.weekday() < 5:
        HIST.append({"dttm": _day.strftime("%a %b %d %Y 00:00:00"), "vole": str(2000 + 37 * len(HIST) % 900),
                     "vale1": f"{5200 + 6 * len(HIST) + 40 * ((len(HIST) % 10) - 5):.2f}"})
    _day += __import__("datetime").timedelta(days=1)
HIST_12M = {"CurrDate": "Mon Oct 19 2026 00:00:00", "CurrTime": "00:00", "CurrVal": HIST[-1]["vale1"], "Data": json.dumps(HIST),
            "HighVal": "8000", "LowVal": "4000", "PrevClose": "0", "Scripname": "ABB"}

RESULTS_FIX = {"col1": "(in Cr.)", "col2": "Jun-26", "col3": "Mar-26", "col4": "FY25-25",
               "resultinCr": [{"title": "Revenue", "v1": "3,558.87", "v2": "3,184.06", "v3": "13,202.73"}, {"title": "Net Profit", "v1": "362.30", "v2": "1,783.65", "v3": "1,668.26"}],
               "resultinS": [{"FY": "FY25-25", "LQ": "Jun-26", "SQ": "Mar-26", "LFY": "https://www.bseindia.com/corporates/results.aspx?Code=500002&Company=ABB-India-Ltd&qtr=128.50&RType=",
                              "LLQ": "https://www.bseindia.com/corporates/results.aspx?Code=500002&Company=ABB-India-Ltd&qtr=130.00&RType=", "LSQ": "x&qtr=129.00&"}]}
ABB = {"FACE_VALUE": "2.00", "GROUP": "A", "INDUSTRY": None, "ISIN_NUMBER": "INE117A01022", "Issuer_Name": "ABB India Limited", "Mktcap": "145561.98",
       "NSURL": "https://www.bseindia.com/stock-share-price/abb-india-ltd/abb/500002/", "SCRIP_CD": "500002", "Scrip_Name": "ABB India Ltd", "Segment": "Equity", "Status": "Active", "scrip_id": "ABB"}
LIST = [ABB, {**ABB, "SCRIP_CD": "500003", "scrip_id": "AEGISLOG", "Scrip_Name": "Aegis Logistics Ltd", "Issuer_Name": "Aegis Logistics Ltd.", "ISIN_NUMBER": "INE208C01025"},
        {**ABB, "SCRIP_CD": "500488", "scrip_id": "ABBOTINDIA", "Scrip_Name": "Abbott India Ltd", "Issuer_Name": "Abbott India Limited", "ISIN_NUMBER": "INE358A01014"}]

FIX = {
    "getScripHeaderData": {"Cmpname": {"Category": "Listed", "EquityScrips": "500002", "FullN": "ABB India Ltd", "SEOUrlEQ": "/stock-share-price/abb-india-ltd/abb/500002/", "ShortN": "abb"},
                           "CurrRate": {"Chg": "+186.75", "LTP": "6963.00", "PcChg": "+2.76"},
                           "Header": {"ASMText": "", "GSMText": "", "High": "6979.00", "LTP": "6963.00", "Low": "6822.45", "Open": "6834.95", "PrevClose": "6776.25", "Ason": "12 Oct 26 | 11:25", "Noticecnt": "3"}},
    "ComHeadernew_par": {"CEPS": "148.44", "ConCEPS": "148.44", "ConEPS": "141.00", "ConNPM": "0.00", "ConOPM": "0.00", "ConPB": None, "ConPE": "49.38", "ConROE": None, "EPS": "141.00", "FaceVal": "2.00", "Group": "A",
                         "IGroup": "Electrical Equipment", "ISIN": "INE117A01022", "ISubGroup": "Heavy Electrical Equipment", "Index": "BSE 200", "Industry": "Heavy Electrical Equipment", "IndustryNew": "Capital Goods",
                         "NPM": "10.18", "OPM": "15.17", "PB": "20.85", "PE": "49.38", "ROE": "42.23", "Sector": "Industrials", "SecurityCode": "500002", "SecurityId": "ABB", "SetlType": "T+1"},
    "MarketDepth": {"BPrice1": "6,962.50", "BPrice2": "6,962.45", "BPrice3": "6,962.25", "BPrice4": "6,962.20", "BPrice5": "6,962.15", "BQty1": "26", "BQty2": "20", "BQty3": "1", "BQty4": "5", "BQty5": "1",
                    "SPrice1": "6,971.40", "SPrice2": "6,971.45", "SPrice3": "6,971.50", "SPrice4": "6,971.55", "SPrice5": "6,971.60", "SQty1": "3", "SQty2": "2", "SQty3": "2", "SQty4": "2", "SQty5": "2",
                    "TotalBQty": "9,390", "TotalSQty": "9,084", "dttm": "12 Oct 2026", "source": "DB"},
    "StockTrading": {"CktLimit": "4,045.00/6,098.65", "ExDate": "07 Aug 2026", "MktCapFF": "36,330.06", "MktCapFull": "1,47,551.80", "TTQ": "4045", "TTQin": "", "Turnover": "2.79", "Turnoverin": "(Cr.)", "TwoWkAvgQty": "0.12", "TwoWkAvgQtyin": "(Lakh)", "WAP": "6,907.07"},
    "HighLow": {"Fifty2WkHigh_unadj": "7923.35 (16/07/2026)", "Fifty2WkLow_unadj": "4640.50 (21/01/2026)", "MonthHighLow": "7434.35 / 6580.00", "WeekHighLow": "7137.20 / 6580.00"},
    "PriceBand": {"LowerT": "6,098.65", "UpperT": "7,453.85", "PBpcLC": "10", "PBpcUC": "10", "PBdate": "12 Oct 2026"},
    "SecurityPosition": json.dumps({"TradeDate": "12 Oct 2026 |10:59", "QtyTraded": "3,664", "DeliverableQty": "2,355", "PcDQ_TQ": "64.27"}),
    "StockReachGraphCas": {"CurrDate": "Mon Oct 12 2026 11:24:59", "CurrVal": "6963.00", "Data": json.dumps(pts), "HighVal": "7000", "LowVal": "6750", "PrevClose": "6776.25", "Scripname": "ABB"},
    "EQPeerGp": {"Table": [{"Name": n, "scrip_cd": c, "LTP": l, "Change": ch, "PE": pe, "PB": 0, "EPS": 141, "Revenue": 3558.87, "PAT": 362.3, "OPM": 15.17, "NPM": 10.18, "w52hi": 7923.35, "w52lo": 4640.5, "Results_QuarterName": "Jun - 26"}
                          for n, c, l, ch, pe in [("ABB", 500002, 6963, 2.76, 49.38), ("Siemens", 500550, 3100, -0.4, 61.2), ("Hitachi Energy", 543187, 18000, 1.1, 120.5), ("CG Power", 500093, 700, 0.2, 80.1)]]},
    "NEWS": json.dumps([{"Newsid": "09f01dde", "NewsSubj": "Announcement under Regulation 30 (LODR)-Change in Management", "Newsdt": "06/10/2026"},
                        {"Newsid": "542b04fc", "NewsSubj": "<img src=x onerror=window.__pwned=1>Closure of Trading Window", "Newsdt": "10/09/2026"}]),
    "RESULTS": json.dumps(RESULTS_FIX),
    "ScripwiseCautionaryMsg": {"Table": [], "Table1": []},
    "LeftMenunew": {"EQSEOurl": "/stock-share-price/abb-india-ltd/abb/500002/", "showResults": True},
    "ddlGroup": [{"GROUP_CODE": g} for g in ["A", "B", "T", "X", "Z"]],
    "GetQuoteAllSearchDatabeta": [{"strSricpCode": "500002", "shortName": "ABB", "scripName": "ABB India Ltd", "Isin": "INE117A01022", "SEOUrl": "https://www.bseindia.com/stock-share-price/abb-india-ltd/abb/500002/", "Type": "in Equity T+1"},
                                  {"strSricpCode": "500488", "shortName": "ABBOTINDIA", "scripName": "Abbott India Ltd", "Isin": "INE358A01014", "SEOUrl": "x", "Type": "in Equity T+1"},
                                  {"strSricpCode": "500002", "shortName": "ABB", "scripName": "ABB India Ltd", "Isin": "INE117A01022", "SEOUrl": "y", "Type": "in Derivatives"}],
}

mode = {"fail": set(), "unmocked": [], "calls": [], "hold": set(), "held": [], "ann": []}

