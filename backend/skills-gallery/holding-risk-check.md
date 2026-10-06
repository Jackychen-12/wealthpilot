---
name: holding-risk-check
description: 持仓风险排查——不看赚了多少，只找组合里最可能出事的地方
whenToUse: 用户想知道自己的组合哪里最危险、最该先处理什么的时候
user-invocable: true
metadata:
  wealthpilot:
    label: 持仓风险排查
    triggers: [风险排查, 持仓风险排查, 哪里最危险, 最该处理什么, 组合有什么隐患]
    needs: holdings
    agents: [portfolio]
    sections: [结论, 集中度, 回撤, 同涨同跌, 最该先处理的一项]
    criteria:
      - 各持仓占比与集中度
      - 各持仓的回撤情况
      - 持仓之间的相关性
      - 按风险画像的约束校验结果
---

# 持仓风险排查

- portfolio: 依次做四件事。用 compute_concentration 看有没有单一持仓占比过高；用回撤分析看哪只跌得最深、有没有恢复；用相关性矩阵看哪些持仓其实是同一个风险（比如直接持有的白酒股和白酒基金）；用 lookthrough_portfolio 看穿透到个股之后真实的暴露集中在哪。最后用 check_profile_constraint 对照风险画像。

不要平均用力。「最该先处理的一项」只写一项：把上面发现的问题排个序，说明为什么是它。没有做风险测评时，只指出问题，不给具体的调仓比例。
