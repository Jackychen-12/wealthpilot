---
name: dividend-check
description: 高股息检查——这只股票的分红能不能持续，现在的股息率值不值得拿
whenToUse: 用户关心分红、股息率、收息、红利股的时候
user-invocable: true
metadata:
  wealthpilot:
    label: 高股息检查
    triggers: [高股息, 股息率, 分红稳不稳, 分红能持续, 红利股, 收息]
    needs: stock
    agents: [fundamental, valuation]
    sections: [结论, 分红记录, 分红能力, 估值, 风险]
    criteria:
      - 最近几年的分红方案与股息率
      - 净利润、经营现金流与资产负债率
      - 当前估值及历史分位
---

# 高股息检查

目的不是找股息率最高的股票，而是判断这份分红靠不靠得住。

- fundamental: 查分红记录（get_dividend_history）和多期财务指标。重点看三件事：分红是不是连续的、每股经营现金流能不能覆盖每股分红、资产负债率有没有在上升。净利润下滑而分红不降的，要指出这是在吃老本。
- valuation: 查估值历史分位和同行对比。股息率高有两种来历：分红多，或者股价跌得多。结合 PE / PB 分位说清楚是哪一种。

成文时在「分红能力」一节直接回答：按最近一期的盈利和现金流，这个分红水平能不能维持。
