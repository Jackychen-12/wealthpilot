"""持仓穿透测试。

网络那层只负责取回字符串，解析与汇总都是纯函数 —— 用真实响应的结构片段
做夹具，脱网也能完整覆盖。
"""

from datetime import date

import pytest

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.lookthrough import (
    aggregate_exposure,
    overlap_between,
    parse_holdings_html,
    summarize_overlap,
)

# 结构照搬东财 f10 的真实返回（两个季度、每季一个 boxitem）
FIXTURE = """var apidata={ content:"
<div class='box'>
<div class='boxitem w790'><h4 class='t'><label class='left'>2026年2季度股票投资明细</label>
<label class='right lab2 xq505'>截止至：<font class='px12'>2026-06-30</font></label></h4>
<table><thead><tr><th>序号</th><th>股票代码</th><th>股票名称</th><th>最新价</th><th>涨跌幅</th><th>相关资讯</th><th>占净值比例</th><th>持股数</th><th>持仓市值</th></tr></thead>
<tbody>
<tr><td>1</td><td>600519</td><td><a>贵州茅台</a></td><td>--</td><td>--</td><td>股吧行情</td><td class='tor'>9.23%</td><td>52.77</td><td>62,558.31</td></tr>
<tr><td>2</td><td>000858</td><td><a>五粮液</a></td><td>--</td><td>--</td><td>股吧行情</td><td class='tor'>6.10%</td><td>120.00</td><td>41,300.00</td></tr>
<tr><td>3</td><td>300750</td><td><a>宁德时代</a></td><td>--</td><td>--</td><td>股吧行情</td><td class='tor'>4.50%</td><td>80.00</td><td>30,000.00</td></tr>
</tbody></table></div>
<div class='boxitem w790'><h4 class='t'><label class='left'>2026年1季度股票投资明细</label>
<label class='right lab2 xq505'>截止至：<font class='px12'>2026-03-31</font></label></h4>
<table><tbody>
<tr><td>1</td><td>601318</td><td><a>中国平安</a></td><td>--</td><td>--</td><td>股吧行情</td><td class='tor'>8.00%</td><td>10</td><td>1</td></tr>
</tbody></table></div>
</div>",arryear:[2026,2025]};"""


def holding(code: str, shares: float) -> PortfolioHolding:
    return PortfolioHolding(
        user_id=1, fund_code=code, fund_name=f"基金{code}", shares=shares,
        cost_price=1.0, buy_date=date(2026, 1, 1), category="equity",
    )


def fund(code: str, stocks: list[tuple[str, str, float]], report="2026-06-30") -> dict:
    return {
        "fund_code": code,
        "report_date": report,
        "stocks": [
            {"stock_code": c, "stock_name": n, "weight_pct": w} for c, n, w in stocks
        ],
        "coverage_pct": round(sum(w for _, _, w in stocks), 2),
    }


class TestParser:
    def test_takes_latest_quarter_only(self):
        """页面含多个季度，只能取最近一期，不能把上季度混进来。"""
        out = parse_holdings_html(FIXTURE)
        assert out["report_date"] == "2026-06-30"
        codes = [s["stock_code"] for s in out["stocks"]]
        assert codes == ["600519", "000858", "300750"]
        assert "601318" not in codes

    def test_strips_tags_from_names(self):
        out = parse_holdings_html(FIXTURE)
        assert out["stocks"][0]["stock_name"] == "贵州茅台"

    def test_parses_weights(self):
        out = parse_holdings_html(FIXTURE)
        assert out["stocks"][0]["weight_pct"] == pytest.approx(9.23)

    def test_coverage_is_sum_of_weights(self):
        out = parse_holdings_html(FIXTURE)
        assert out["coverage_pct"] == pytest.approx(19.83)

    def test_empty_input_is_safe(self):
        out = parse_holdings_html("")
        assert out["stocks"] == [] and out["coverage_pct"] == 0.0

    def test_garbage_input_is_safe(self):
        assert parse_holdings_html("<html>404</html>")["stocks"] == []


class TestOverlap:
    def test_shared_stocks_found(self):
        a = fund("A", [("600519", "贵州茅台", 9.0), ("000858", "五粮液", 6.0)])
        b = fund("B", [("600519", "贵州茅台", 5.0), ("300750", "宁德时代", 7.0)])
        out = overlap_between(a, b)
        assert out["shared_count"] == 1
        assert out["shared_stocks"][0]["stock_code"] == "600519"

    def test_combined_weight_uses_min(self):
        """共同暴露取两侧较小值 —— 保守且好解释。"""
        a = fund("A", [("600519", "贵州茅台", 9.0)])
        b = fund("B", [("600519", "贵州茅台", 5.0)])
        assert overlap_between(a, b)["combined_weight_pct"] == pytest.approx(5.0)

    def test_no_overlap(self):
        a = fund("A", [("600519", "贵州茅台", 9.0)])
        b = fund("B", [("300750", "宁德时代", 7.0)])
        out = overlap_between(a, b)
        assert out["shared_count"] == 0
        assert out["combined_weight_pct"] == 0

    def test_report_dates_carried(self):
        a = fund("A", [("600519", "x", 1.0)], report="2026-06-30")
        b = fund("B", [("600519", "x", 1.0)], report="2026-03-31")
        assert overlap_between(a, b)["report_dates"]["B"] == "2026-03-31"


class TestAggregateExposure:
    def test_exposure_is_fund_weight_times_stock_weight(self):
        """A 占组合 50%，茅台占 A 的 10% → 穿透暴露 5%。"""
        h = [holding("A", 100), holding("B", 100)]
        nav = {"A": 1.0, "B": 1.0}
        fh = {"A": fund("A", [("600519", "贵州茅台", 10.0)]),
              "B": fund("B", [("300750", "宁德时代", 10.0)])}
        out = aggregate_exposure(h, nav, fh)
        by_code = {s["stock_code"]: s for s in out["stocks"]}
        assert by_code["600519"]["exposure_pct"] == pytest.approx(5.0)

    def test_multi_fund_stock_flagged(self):
        h = [holding("A", 100), holding("B", 100)]
        nav = {"A": 1.0, "B": 1.0}
        fh = {"A": fund("A", [("600519", "贵州茅台", 10.0)]),
              "B": fund("B", [("600519", "贵州茅台", 8.0)])}
        out = aggregate_exposure(h, nav, fh)
        assert len(out["multi_fund_stocks"]) == 1
        # 0.5*10 + 0.5*8 = 9
        assert out["multi_fund_exposure_pct"] == pytest.approx(9.0)

    def test_sorted_by_exposure(self):
        h = [holding("A", 100)]
        fh = {"A": fund("A", [("1", "小", 2.0), ("2", "大", 9.0)])}
        out = aggregate_exposure(h, {"A": 1.0}, fh)
        assert out["stocks"][0]["stock_name"] == "大"

    def test_uncovered_funds_counted(self):
        """拿不到季报的基金要如实计数，不能假装穿透完整。"""
        h = [holding("A", 100), holding("B", 100)]
        fh = {"A": fund("A", [("1", "x", 5.0)]), "B": {"fund_code": "B", "stocks": []}}
        out = aggregate_exposure(h, {"A": 1.0, "B": 1.0}, fh)
        assert out["covered_fund_count"] == 1
        assert out["total_fund_count"] == 2

    def test_carries_staleness_caveat(self):
        h = [holding("A", 100)]
        out = aggregate_exposure(h, {"A": 1.0}, {"A": fund("A", [("1", "x", 5.0)])})
        assert "滞后" in out["note"] and "前十大" in out["note"]
        assert out["report_dates"]["A"] == "2026-06-30"

    def test_empty_portfolio(self):
        assert aggregate_exposure([], {}, {})["stocks"] == []


class TestSummary:
    def test_summary_mentions_count_and_weight(self):
        h = [holding("A", 100), holding("B", 100)]
        fh = {"A": fund("A", [("600519", "贵州茅台", 10.0)]),
              "B": fund("B", [("600519", "贵州茅台", 8.0)])}
        text = summarize_overlap(aggregate_exposure(h, {"A": 1.0, "B": 1.0}, fh))
        assert "贵州茅台" in text and "1 只" in text

    def test_no_overlap_message(self):
        h = [holding("A", 100)]
        text = summarize_overlap(aggregate_exposure(h, {"A": 1.0}, {"A": fund("A", [("1", "x", 5.0)])}))
        assert "没有交集" in text
