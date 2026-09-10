"""多资产报价测试。网络那层不测，解析与代码映射是纯函数，钉死。"""

import pytest

from wealthpilot.services.assets import CRYPTO_IDS, parse_sina_quote, sina_symbol


class TestSinaSymbol:
    @pytest.mark.parametrize("code,expected", [
        ("600519", "sh600519"),   # 沪市主板
        ("510300", "sh510300"),   # 沪市 ETF
        ("000858", "sz000858"),   # 深市主板
        ("300750", "sz300750"),   # 创业板
        ("159915", "sz159915"),   # 深市 ETF
        ("830799", "bj830799"),   # 北交所
    ])
    def test_prefix_inferred(self, code, expected):
        assert sina_symbol(code) == expected

    def test_existing_prefix_kept(self):
        assert sina_symbol("sh600519") == "sh600519"
        assert sina_symbol("SZ000858") == "sz000858"

    def test_whitespace_tolerated(self):
        assert sina_symbol("  600519 ") == "sh600519"


class TestParseSinaQuote:
    LINE = ("贵州茅台,1291.000,1290.880,1283.620,1294.990,1282.000,1283.600,1283.630,"
            "1474092,1894349927.000") + ",0" * 20 + ",2026-09-10,14:05:33,00,"

    def test_parses_price_and_change(self):
        q = parse_sina_quote(self.LINE)
        assert q["name"] == "贵州茅台"
        assert q["price"] == pytest.approx(1283.62)
        assert q["prev_close"] == pytest.approx(1290.88)
        # (1283.62 - 1290.88) / 1290.88 * 100 = -0.5624...
        assert q["change_pct"] == pytest.approx(-0.56, abs=0.01)

    def test_suspended_stock_is_invalid(self):
        """停牌时现价为 0 —— 应视为无效报价，而不是"价格是 0"。"""
        assert parse_sina_quote("某股票,0,0,0,0,0") is None

    def test_empty_line_is_none(self):
        assert parse_sina_quote("") is None
        assert parse_sina_quote(",,,,,") is None

    def test_too_few_fields(self):
        assert parse_sina_quote("名称,1,2") is None

    def test_non_numeric_is_none(self):
        assert parse_sina_quote("名称,-,-,-,-,-") is None

    def test_zero_prev_close_does_not_divide_by_zero(self):
        q = parse_sina_quote("新股,10,0,12,12,10")
        assert q is not None and q["change_pct"] == 0.0


class TestCryptoMapping:
    def test_common_symbols_present(self):
        for sym in ("BTC", "ETH", "USDT"):
            assert sym in CRYPTO_IDS

    def test_maps_to_coingecko_ids(self):
        assert CRYPTO_IDS["BTC"] == "bitcoin"
        assert CRYPTO_IDS["ETH"] == "ethereum"
