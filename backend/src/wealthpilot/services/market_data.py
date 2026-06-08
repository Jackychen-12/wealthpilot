"""行情数据服务 — 多源聚合。

免费数据源：
1. AKShare（核心）— 基金净值/指数/行业/宏观，完全免费无限制
2. 天天基金 HTTP API — 实时估值 + 基金详情
3. 东方财富 HTTP API — 指数行情 + 资讯
4. 新浪财经 API — 实时股票/指数报价
5. 网易财经 — 历史行情数据
"""

import json
from datetime import date, datetime, timedelta

import httpx


# ═══════════════════════════════════════════════════════════
# AKShare 数据（核心，本地 Python 调用，无 API 限制）
# ═══════════════════════════════════════════════════════════

def get_fund_nav_akshare(fund_code: str, days: int = 60) -> list[dict]:
    """用 AKShare 拉基金历史净值（推荐，无频率限制）。"""
    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        if df is None or df.empty:
            return []
        # 取最近 N 天
        df = df.tail(days)
        records = []
        for _, row in df.iterrows():
            nav_date = row["净值日期"]
            if hasattr(nav_date, "strftime"):
                nav_date = nav_date.strftime("%Y-%m-%d")
            records.append({
                "fund_code": fund_code,
                "nav_date": str(nav_date),
                "nav": float(row["单位净值"]),
                "acc_nav": float(row.get("累计净值", 0) or 0),
                "daily_return": float(row.get("日增长率", 0) or 0),
            })
        return list(reversed(records))  # 最新在前
    except Exception:
        return []


def get_fund_detail_akshare(fund_code: str) -> dict | None:
    """用 AKShare 获取基金详细信息（经理/规模/类型/成立日期等）。"""
    try:
        import akshare as ak
        df = ak.fund_individual_basic_info_xq(symbol=fund_code)
        if df is None or df.empty:
            return None
        info = {}
        for _, row in df.iterrows():
            info[row.iloc[0]] = row.iloc[1]
        return {
            "code": fund_code,
            "name": info.get("基金简称", ""),
            "type": info.get("基金类型", ""),
            "manager": info.get("基金经理", ""),
            "company": info.get("基金公司", ""),
            "scale": info.get("基金规模", ""),
            "establish_date": info.get("成立日期", ""),
            "benchmark": info.get("业绩比较基准", ""),
        }
    except Exception:
        return None


def get_index_data_akshare() -> list[dict]:
    """用 AKShare 获取主要指数实时数据。"""
    try:
        import akshare as ak
        # A 股主要指数
        indices = [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sz399006", "创业板指"),
        ]
        results = []
        for code, name in indices:
            try:
                market = "sh" if code.startswith("sh") else "sz"
                symbol = code[2:]
                df = ak.stock_zh_index_spot_em()
                row = df[df["代码"] == symbol]
                if not row.empty:
                    close = float(row.iloc[0]["最新价"])
                    change = float(row.iloc[0]["涨跌幅"])
                    results.append({
                        "name": name,
                        "value": f"{close:,.2f}",
                        "change": f"{'+' if change >= 0 else ''}{change:.2f}%",
                        "up": change >= 0,
                    })
                else:
                    results.append({"name": name, "value": "--", "change": "--", "up": False})
            except Exception:
                results.append({"name": name, "value": "--", "change": "--", "up": False})
        return results
    except Exception:
        return []


def get_fund_rank_akshare(fund_code: str) -> dict | None:
    """获取基金排名信息。"""
    try:
        import akshare as ak
        df = ak.fund_open_fund_rank_em(symbol="全部")
        if df is None or df.empty:
            return None
        row = df[df["基金代码"] == fund_code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "code": fund_code,
            "name": str(r.get("基金简称", "")),
            "nav": float(r.get("单位净值", 0) or 0),
            "return_1w": str(r.get("近1周", "")),
            "return_1m": str(r.get("近1月", "")),
            "return_3m": str(r.get("近3月", "")),
            "return_6m": str(r.get("近6月", "")),
            "return_1y": str(r.get("近1年", "")),
        }
    except Exception:
        return None


def get_macro_data_akshare() -> dict:
    """获取宏观经济指标（GDP/CPI/PMI 等）。"""
    try:
        import akshare as ak
        result = {}
        # PMI
        try:
            pmi = ak.macro_china_pmi_yearly()
            if pmi is not None and not pmi.empty:
                latest = pmi.iloc[-1]
                result["pmi"] = {"date": str(latest.iloc[0]), "value": float(latest.iloc[1])}
        except Exception:
            pass
        # CPI
        try:
            cpi = ak.macro_china_cpi_yearly()
            if cpi is not None and not cpi.empty:
                latest = cpi.iloc[-1]
                result["cpi"] = {"date": str(latest.iloc[0]), "value": float(latest.iloc[1])}
        except Exception:
            pass
        return result
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
# 天天基金 HTTP API（实时估值，适合盘中）
# ═══════════════════════════════════════════════════════════

async def fetch_fund_nav(fund_code: str, days: int = 30) -> list[dict]:
    """拉取基金近 N 天净值（天天基金 HTTP API）。"""
    url = "https://api.fund.eastmoney.com/f10/lsjz"
    params = {"fundCode": fund_code, "pageIndex": 1, "pageSize": days}
    headers = {"Referer": "https://fundf10.eastmoney.com/"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        records = []
        for item in data.get("Data", {}).get("LSJZList", []):
            try:
                records.append({
                    "fund_code": fund_code,
                    "nav_date": item["FSRQ"],
                    "nav": float(item["DWJZ"]),
                    "acc_nav": float(item.get("LJJZ", 0) or 0),
                    "daily_return": float(item.get("JZZZL", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
        return records
    except Exception:
        # fallback 到 AKShare
        return get_fund_nav_akshare(fund_code, days)


async def fetch_fund_info(fund_code: str) -> dict | None:
    """拉取基金实时估值（盘中有效）。"""
    url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
            json_str = text[text.index("{"):text.rindex("}") + 1]
            data = json.loads(json_str)
            return {
                "code": data.get("fundcode", fund_code),
                "name": data.get("name", ""),
                "nav": float(data.get("dwjz", 0)),
                "nav_date": data.get("jzrq", ""),
                "estimated_nav": float(data.get("gsz", 0) or 0),
                "estimated_change": float(data.get("gszzl", 0) or 0),
                "update_time": data.get("gztime", ""),
            }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# 东方财富 / 新浪 — 指数 + 资讯
# ═══════════════════════════════════════════════════════════

async def fetch_indices() -> list[dict]:
    """拉取主要指数行情（多源 fallback）。"""
    # 先试 AKShare
    akshare_result = get_index_data_akshare()
    if akshare_result and any(r["value"] != "--" for r in akshare_result):
        return akshare_result

    # fallback：新浪财经实时接口
    sina_codes = ["s_sh000001", "s_sz399001", "s_sz399006"]
    names = ["上证指数", "深证成指", "创业板指"]
    results = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://hq.sinajs.cn/list={','.join(sina_codes)}",
                headers={"Referer": "https://finance.sina.com.cn"},
            )
            lines = resp.text.strip().split("\n")
            for i, line in enumerate(lines):
                try:
                    parts = line.split('"')[1].split(",")
                    name = names[i]
                    close = float(parts[1])
                    change_pct = float(parts[3])
                    results.append({
                        "name": name,
                        "value": f"{close:,.2f}",
                        "change": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
                        "up": change_pct >= 0,
                    })
                except (IndexError, ValueError):
                    results.append({"name": names[i], "value": "--", "change": "--", "up": False})
    except Exception:
        results = [{"name": n, "value": "--", "change": "--", "up": False} for n in names]
    return results


async def fetch_market_news() -> list[dict]:
    """拉取财经要闻（东方财富）。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
                params={"columns": "102", "pageSize": 8, "pageIndex": 0},
            )
            data = resp.json()
            news = []
            for item in data.get("data", {}).get("list", [])[:8]:
                title = item.get("title", "")
                # 自动打 tag
                tag = "财经"
                if any(k in title for k in ["美股", "纳斯达克", "标普"]):
                    tag = "美股"
                elif any(k in title for k in ["港股", "恒生", "恒指"]):
                    tag = "港股"
                elif any(k in title for k in ["A股", "沪指", "创业板", "上证"]):
                    tag = "A股"
                elif any(k in title for k in ["基金", "ETF"]):
                    tag = "基金"
                elif any(k in title for k in ["政策", "央行", "监管"]):
                    tag = "政策"
                news.append({"tag": tag, "text": title[:60]})
            return news if news else [{"tag": "市场", "text": "暂无最新资讯"}]
    except Exception:
        return [{"tag": "市场", "text": "资讯加载失败，请稍后刷新"}]


# ═══════════════════════════════════════════════════════════
# 综合查询接口（给 Agent tool 用）
# ═══════════════════════════════════════════════════════════

async def get_comprehensive_fund_info(fund_code: str) -> dict:
    """综合基金信息（估值 + 详情 + 排名）。"""
    realtime = await fetch_fund_info(fund_code)
    detail = get_fund_detail_akshare(fund_code)
    rank = get_fund_rank_akshare(fund_code)

    result = {"code": fund_code}
    if realtime:
        result.update(realtime)
    if detail:
        result["manager"] = detail.get("manager", "")
        result["company"] = detail.get("company", "")
        result["scale"] = detail.get("scale", "")
        result["type"] = detail.get("type", "")
        result["benchmark"] = detail.get("benchmark", "")
    if rank:
        result["return_1w"] = rank.get("return_1w", "")
        result["return_1m"] = rank.get("return_1m", "")
        result["return_3m"] = rank.get("return_3m", "")
        result["return_1y"] = rank.get("return_1y", "")

    return result
