"""周报 PDF 导出测试。

不解析 PDF 内容（那需要额外依赖），只验证真正生成了 PDF、中文不崩、
以及结构缺字段时不炸 —— 原实现输出的是 .txt，"是不是真 PDF" 正是关键断言。
"""

from wealthpilot.services.pdf_report import build_weekly_pdf

REPORT = {
    "week_start": "2026-09-07",
    "week_end": "2026-09-11",
    "summary": "本周组合收益 -1 元，涨幅 -0.39%。",
    "key_points": ["贵州茅台：贡献 -0.2%", "沪深300ETF：贡献 -0.1%"],
    "next_week_focus": ["三季报预告", "上游价格走势"],
    "risks": ["单一行业占比偏高"],
    "ai_insights": "组合波动主要来自权益仓位。",
}


class TestBuild:
    def test_produces_real_pdf(self):
        pdf = build_weekly_pdf(REPORT)
        assert pdf.startswith(b"%PDF-"), "输出不是 PDF"
        assert pdf.rstrip().endswith(b"%%EOF")
        assert len(pdf) > 1000

    def test_chinese_does_not_crash(self):
        """中文 PDF 的常见死法是字体缺失 —— 用内置 CID 字体规避。"""
        pdf = build_weekly_pdf({**REPORT, "summary": "组合回撤 −18.62%，白酒行业拖累明显。"})
        assert pdf.startswith(b"%PDF-")

    def test_minimal_report_works(self):
        assert build_weekly_pdf({}).startswith(b"%PDF-")

    def test_missing_optional_sections(self):
        pdf = build_weekly_pdf({"week_start": "a", "week_end": "b", "summary": "s"})
        assert pdf.startswith(b"%PDF-")

    def test_with_portfolio_summary(self):
        summary = {"total_market_value": 12345.6, "total_cost": 10000,
                   "total_return": 2345.6, "return_pct": 23.45}
        pdf = build_weekly_pdf(REPORT, summary)
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > len(build_weekly_pdf(REPORT))

    def test_string_sections_accepted(self):
        """key_points 可能是字符串而非列表，不该因此报错。"""
        assert build_weekly_pdf({**REPORT, "key_points": "单条要点"}).startswith(b"%PDF-")

    def test_repeated_calls_reuse_font(self):
        """字体重复注册会抛错，必须是幂等的。"""
        for _ in range(3):
            assert build_weekly_pdf(REPORT).startswith(b"%PDF-")
