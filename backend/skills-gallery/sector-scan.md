---
name: sector-scan
description: 行业扫描——快速摸清一个行业：最近表现、里面有哪些公司、哪几家值得深入看
whenToUse: 用户想了解一个行业、还没有具体标的的时候
user-invocable: true
metadata:
  wealthpilot:
    label: 行业扫描
    triggers: [行业扫描, 扫描一下行业, 这个行业怎么样, 行业里有哪些公司]
    needs: none
    agents: [industry, screener]
    sections: [结论, 行业表现, 行业内的公司, 值得深入看的, 局限]
    criteria:
      - 行业当日表现与市场概况
      - 按行业筛出的公司名单及其估值、盈利指标
---

# 行业扫描

- industry: 查当日行业涨跌排行和大盘概况，说明用户问的这个行业今天处在什么位置；再查相关的财经新闻。
- screener: 用 screen_stocks 按行业筛选，按总市值排序取前若干只，列出市值、PE、PB、年化 ROE、营收与净利同比。行业名称要用筛选工具认得的写法；筛不出来就换一个相近的行业名再试一次，并说明用了哪个名称。

「值得深入看的」一节只挑两到三家，每家一句理由（比如行业里 ROE 最高、估值最低、增速最快），并提醒这只是按数字挑的，要判断还得单独做深度研究。
