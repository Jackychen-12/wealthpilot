---
name: earnings-check
description: 财报季检查——新财报出来后，快速判断这份业绩是超预期的好、符合预期，还是有隐患
whenToUse: 用户让解读刚发布的季报、中报、年报的时候
user-invocable: true
metadata:
  wealthpilot:
    label: 财报季检查
    triggers: [解读财报, 财报解读, 这份财报, 新财报, 季报怎么样, 中报怎么样, 年报怎么样]
    needs: stock
    agents: [fundamental, industry]
    sections: [结论, 业绩数字, 管理层怎么说, 数字和说法对不对得上, 后续盯什么]
    criteria:
      - 最新一期营收、净利润、扣非净利润及同比
      - 定期报告正文中管理层对业绩变动的解释
---

# 财报季检查

- fundamental: 先取多期财务指标，再用 read_latest_report 读「管理层讨论」和「业绩变动原因」。对比三组数：营收与净利润的增速差、净利润与扣非净利润的差、利润与经营现金流的差。任何一组明显背离都要点出来。
- industry: 查这份财报披露前后的公告（业绩预告、更正、问询函），有的话读正文；再看同行业已披露公司的大致情况。

成文时「数字和说法对不对得上」一节是重点：管理层说的原因，能不能在财务数字里找到对应。对不上的直接写对不上。
