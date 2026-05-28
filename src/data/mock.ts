export const marketIndices = [
  { name: '上证指数', value: '3,957.05', change: '+1.24%', up: true },
  { name: '恒生指数', value: '25,277.32', change: '-0.88%', up: false },
  { name: '纳斯达克', value: '21,647.61', change: '+2.01%', up: true },
]

export const marketNews = [
  { tag: 'A股', text: '上证指数创年内新低，创业板指创4年新高...' },
  { tag: '港股', text: '恒指收跌，科技指数重挫，能源与锂电板...' },
  { tag: '美股', text: '三大指数全线重挫，科技股遭抛售...' },
  { tag: '黄金', text: '黄金价格遭遇历史级暴跌，单周跌幅创43...' },
]

export const headlines = [
  { tag: '国际', text: '巴林铝业关停19%产能，国际铝价飙升至四...' },
  { tag: '政策', text: '新增建设用地原则上不用于经营性房地产开发' },
  { tag: '油价', text: '布油周涨8.77%破112美元，中东局势推高...' },
]

export const portfolioSummary = {
  weeklyReturn: '+1,280',
  weeklyGrowth: '+1.42%',
  excessReturn: '+0.67%',
  volatility: '稳健',
  description:
    '本周组合收益 +1,280元（+1.42%），跑赢沪深300指数0.67个百分点。主要贡献来自半导体主题基金，受益于AI算力需求持续扩张。',
  fullDescription:
    '本周组合收益 +1,280元（+1.42%），跑赢沪深300指数0.67个百分点。主要贡献来自半导体基金（+3.21%），受AI算力政策利好。医疗板块拖累（-1.85%）。',
}

export const topContributors = [
  { tag: '主要贡献', name: '国泰半导体芯片ETF联接', value: '+3.21%', positive: true },
  { tag: '稳定收益', name: '易方达中短期债券A', value: '+0.12%', positive: true },
]

export const topDetractors = [
  { tag: '需关注', name: '中欧医疗健康混合A', value: '-1.85%', positive: false },
]

export const attributionByFund = [
  { name: '国泰半导体芯片ETF联接', value: '+820元', pct: 85, positive: true },
  { name: '富国天惠成长混合', value: '+340元', pct: 45, positive: true },
  { name: '易方达中短期债券A', value: '+120元', pct: 18, positive: true },
  { name: '中欧医疗健康混合A', value: '-520元', pct: 55, positive: false },
]

export const attributionByIndustry = [
  { name: '电子/半导体', value: '+780元', pct: 82, positive: true },
  { name: '消费', value: '+240元', pct: 32, positive: true },
  { name: '债券', value: '+120元', pct: 18, positive: true },
  { name: '医药生物', value: '-520元', pct: 55, positive: false },
]

export const attributionByAsset = [
  { name: '权益类基金', value: '+640元', pct: 68, positive: true },
  { name: '债券类基金', value: '+120元', pct: 18, positive: true },
  { name: '货币基金', value: '+0元', pct: 2, positive: false },
]

export const drawdownFunds = [
  { name: '国泰半导体芯片ETF联接', value: '-4.1%', severity: 'high' as const },
  { name: '中欧医疗健康混合A', value: '-2.8%', severity: 'medium' as const },
  { name: '富国天惠成长混合', value: '-1.9%', severity: 'medium' as const },
]

export const historicalDrawdown = [
  { value: '18', label: '平均恢复天数' },
  { value: '-4.3%', label: '平均最大跌幅' },
  { value: '4/5', label: '30日内恢复' },
]

export const riskPoints = [
  { name: '权益仓位集中度偏高（72%）', status: '需注意', severity: 'high' as const },
  { name: '成长风格暴露偏大', status: '关注', severity: 'medium' as const },
  { name: '债基对冲效果正常', status: '正常', severity: 'low' as const },
]

export const healthDimensions = [
  { name: '收益表现', status: '优秀', severity: 'low' as const },
  { name: '波动控制', status: '良好', severity: 'low' as const },
  { name: '持仓分散度', status: '偏低', severity: 'medium' as const },
  { name: '风格匹配度', status: '偏离', severity: 'high' as const },
  { name: '风险收益比', status: '合理', severity: 'low' as const },
]

export const suggestions = [
  {
    title: '了解利率周期对成长股的影响',
    desc: '您的持仓以成长风格为主，利率变动对您影响较大',
    bg: 'primaryLight' as const,
  },
  {
    title: '对比同类医疗基金表现',
    desc: '您的医疗基金近3月跑输同类均值，可横向比较',
    bg: 'warningLight' as const,
  },
  {
    title: '使用 Pilot AI 深入分析持仓',
    desc: '围绕您的组合进行更深度的问答和分析',
    bg: 'primaryLight' as const,
    action: 'chat' as const,
  },
  {
    title: '开启每周AI复盘提醒',
    desc: '每周五收盘后自动生成复盘报告并推送',
    bg: 'successLight' as const,
    toggle: true,
  },
  {
    title: '咨询持牌投顾',
    desc: '连接合作持牌投顾机构，获取个性化建议',
    bg: 'accent' as const,
  },
]

export const watchSignals = [
  { title: '央行逆回购操作变化', desc: '影响成长类持仓估值' },
  { title: '集采政策第九批落地节奏', desc: '直接影响医疗基金表现' },
  { title: '英伟达下季度指引', desc: '利好/利空半导体持仓' },
]

export const weeklyKeyPoints = [
  { title: '半导体基金贡献最大', desc: '+820元，受AI算力需求利好' },
  { title: '医疗基金继续拖累', desc: '-520元，集采政策预期持续压制' },
  { title: '债基部分表现平稳', desc: '+120元，利率波动中提供对冲' },
]

export const weeklyFocus = [
  '周二：3月PMI数据公布，关注制造业景气度',
  '周三：美联储议息会议纪要发布',
  '周五：集采第九批品种目录可能公布',
]

export const chatMessages = [
  {
    role: 'ai' as const,
    content:
      '根据本周复盘结果，您的医疗基金中欧医疗健康混合A连续3周跑输同类平均，主要原因是集采政策扩围预期持续压制医药板块估值。目前该基金经理未发生变更，持仓风格未明显漂移，更多是行业Beta层面的系统性压力。',
  },
  {
    role: 'user' as const,
    content: '那我这只医疗基金还值得继续拿吗？',
  },
  {
    role: 'ai' as const,
    content: 'analysis',
    sections: [
      {
        title: '1. 基金本身',
        text: '该基金经理管理经验5年+，历史回撤控制中等偏上，当前跑输更多来自行业因素而非基金管理问题。',
      },
      {
        title: '2. 行业趋势',
        text: '集采政策对仿制药影响较大，但创新药赛道政策面偏暖。可关注该基金创新药持仓占比。',
      },
      {
        title: '3. 您的组合',
        text: '医疗仓位占总持仓12%，属于中等配置，不构成集中度风险。',
      },
    ],
  },
  {
    role: 'user' as const,
    content: '帮我看看这只基金的创新药持仓占比',
  },
  {
    role: 'ai' as const,
    content: 'table',
    intro: '根据中欧医疗健康混合A最新季报（2024Q4）数据：',
    tableData: [
      { name: '创新药及CXO', value: '38.2%', highlight: true },
      { name: '仿制药及原料药', value: '22.5%', highlight: false },
      { name: '医疗器械', value: '18.7%', highlight: false },
      { name: '医疗服务及其他', value: '20.6%', highlight: false },
    ],
    conclusion:
      '创新药占比38.2%，同类中等偏上。相比上季度提升3.1个百分点，基金经理正在主动调整方向。',
  },
]

export const chatQuickReplies = [
  '这只基金同类排名如何？',
  '和其他医疗基金对比',
  '咨询专业投顾',
]
