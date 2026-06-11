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
  '📊 最新市场动态',
  '💼 分析持仓收益归因',
  '🛡️ 评估回撤风险',
]

export const aiResponses: Record<string, { text: string; followUps: string[]; agent?: string; tools?: string[] }> = {
  '这只基金同类排名如何？': {
    text: '根据最新数据，中欧医疗健康混合A近1年收益率-8.72%，在同类463只偏股混合型基金中排名第312位，处于后30%分位。但近3个月排名有所回升（第178位），主要受益于创新药板块反弹。基金经理葛兰管理该基金超过5年，长期（3年+）业绩仍处于同类前40%。短期排名下滑更多反映行业系统性压力，而非基金管理能力问题。',
    followUps: ['葛兰的其他基金表现如何？', '有没有排名更好的医疗基金？', '什么时候适合加仓？'],
    agent: '📊 市场分析 — 基金排名查询',
    tools: ['get_fund_info', 'get_nav_history'],
  },
  '和其他医疗基金对比': {
    text: '将中欧医疗健康与同类头部医疗基金对比：\n\n1. 工银前沿医疗（近1年 -5.3%）— 偏重医疗器械，受集采影响较小\n2. 广发医疗保健A（近1年 -7.1%）— 均衡配置，创新药+器械各半\n3. 中欧医疗健康A（近1年 -8.7%）— 偏重创新药，弹性大但波动也大\n4. 融通健康产业A（近1年 -11.2%）— 重仓CXO，受海外需求下滑影响\n\n您持有的中欧医疗排名居中，创新药占比最高（38.2%），一旦政策面转暖，反弹空间也最大。如果看好创新药赛道，可以继续持有；如果偏好稳健，可考虑部分转向工银前沿医疗。',
    followUps: ['工银前沿医疗详细分析', '创新药赛道前景如何？', '帮我做一个换仓方案'],
    agent: '🛡️ 风险分析 — 基金对比',
    tools: ['compare_funds', 'get_fund_info', 'calculate_return'],
  },
  '半导体基金还能追吗？': {
    text: '国泰半导体芯片ETF联接本周涨3.21%，年初至今涨18.7%，已经处于相对高位。从几个维度分析：\n\n1. 估值：半导体行业PE（TTM）48倍，处于近5年75%分位，不算便宜但也未到极端\n2. 基本面：AI算力需求持续旺盛，国产替代逻辑未变，但短期利好已部分兑现\n3. 资金面：近1周该ETF净流入12.3亿，市场情绪偏热\n4. 技术面：短期涨幅较大，存在回调整固需求\n\n建议：如果已有仓位（您当前配置占比35%），短期不宜追高加仓。可设定回调5%-8%时分批加仓的计划。当前仓位可继续持有，享受趋势收益。',
    followUps: ['帮我设定一个加仓计划', '半导体之外还有哪些AI受益板块？', '我的半导体仓位是否过重？'],
    agent: '📊 市场分析 — ETF 追踪',
    tools: ['get_fund_info', 'get_nav_history', 'search_news'],
  },
  '葛兰的其他基金表现如何？': {
    text: '葛兰目前管理3只基金，整体表现与医疗行业走势高度相关：\n\n1. 中欧医疗健康混合A — 规模234亿，近1年-8.72%\n2. 中欧医疗创新股票A — 规模89亿，近1年-9.15%（更偏创新药，弹性更大）\n3. 中欧阿尔法混合A — 规模45亿，近1年-3.28%（非纯医疗，配置了部分消费和科技）\n\n如果您看好葛兰但想降低医疗集中度，中欧阿尔法是更均衡的选择。但需注意其与您持有的富国天惠有一定重仓股重叠。',
    followUps: ['中欧阿尔法详细持仓分析', '和富国天惠的重叠度有多少？', '换成中欧阿尔法值得吗？'],
    agent: '📊 市场分析 — 基金经理分析',
    tools: ['get_fund_info', 'compare_funds'],
  },
  '有没有排名更好的医疗基金？': {
    text: '近1年排名前10的医疗主题基金中，有几只值得关注：\n\n1. 华宝医药生物A（近1年+2.1%）— 重仓中药板块，受益于中药创新和国企改革\n2. 工银前沿医疗（近1年-5.3%）— 偏器械，受集采直接影响小\n3. 招商医药健康A（近1年-5.8%）— 均衡配置，回撤控制出色\n\n不过需要注意：排名好的基金多是因为避开了创新药，而创新药目前估值处于历史低位。如果着眼1-2年维度，当前持有创新药占比高的中欧医疗反而可能有更好的赔率。',
    followUps: ['华宝医药生物详细分析', '中药板块前景如何？', '要不要分散到多只医疗基金？'],
    agent: '📊 市场分析 — 基金排名对比',
    tools: ['get_fund_info', 'compare_funds', 'get_nav_history'],
  },
  '什么时候适合加仓？': {
    text: '基于当前市场环境，有几个可参考的加仓信号：\n\n1. 政策信号：集采第九批品种目录公布后，如果集采范围未超预期扩大，将是情绪拐点\n2. 估值信号：医药生物板块PE跌破25倍（当前27.3倍），进入历史底部区域\n3. 资金信号：北向资金连续3日净买入医药板块\n4. 技术信号：板块指数放量突破20日均线\n\n建议设定分批加仓计划：当前仓位12%保持不动，若出现上述2个及以上信号，可分2次加至18%。注意单次加仓金额不超过总资产的3%。\n\n⚠️ 以上仅为分析框架，不构成投资建议。',
    followUps: ['帮我设定自动提醒', '如果集采超预期怎么办？', '目前12%的仓位合理吗？'],
    agent: '🛡️ 风险分析 — 加仓时机评估',
    tools: ['get_nav_history', 'get_drawdown_analysis', 'search_news'],
  },
  '帮我设定一个加仓计划': {
    text: '基于您当前的半导体持仓（国泰半导体芯片ETF联接，占比35%），建议如下加仓计划：\n\n📋 分批加仓方案：\n• 第一档：回调5%（净值跌至1.52附近）→ 加仓总资产的2%\n• 第二档：回调8%（净值跌至1.47附近）→ 再加仓总资产的2%\n• 第三档：回调12%（净值跌至1.41附近）→ 加仓总资产的3%\n\n⚠️ 止损线：如跌破1.35（回调约15%），建议重新评估持仓逻辑\n\n加仓后半导体最高占比将达42%，接近单一行业上限。建议同步考虑降低其他权益仓位以控制整体风险。\n\n⚠️ 以上仅为参考框架，不构成投资建议。',
    followUps: ['42%的占比会不会太高？', '其他仓位怎么调整？', '有没有更稳健的方案？'],
    agent: '💼 持仓分析 — 加仓策略生成',
    tools: ['get_fund_info', 'get_nav_history', 'calculate_position_size'],
  },
  '创新药赛道前景如何？': {
    text: '创新药赛道中长期逻辑依然成立，但短期面临几个关键变量：\n\n利好因素：\n• 国内创新药出海加速，2024年License-out交易金额创历史新高\n• FDA对中国创新药审批态度积极，多款药物获突破性疗法认定\n• 医保谈判规则优化，创新药降价幅度趋缓\n\n压制因素：\n• 美国《生物安全法案》对CXO板块的潜在影响\n• 行业融资环境仍偏紧，部分Biotech公司面临现金流压力\n• 集采向生物药扩展的不确定性\n\n综合判断：创新药板块当前估值处于近5年20%分位，安全边际较高。如果投资周期在1年以上，当前是较好的布局窗口。',
    followUps: ['哪些创新药公司值得关注？', '《生物安全法案》影响有多大？', '帮我分析创新药ETF'],
    agent: '📊 市场分析 — 行业赛道研究',
    tools: ['search_news', 'get_industry_data', 'get_fund_info'],
  },
}

export const defaultResponse: { text: string; followUps: string[]; agent?: string; tools?: string[] } = {
  text: '感谢您的提问。WealthPilot 多智能体系统已为您分析。目前我配备了 12 个实时工具，覆盖市场查询、持仓分析和风险评估三大领域。您可以尝试：\n\n1. 查看市场动态（如"最新财经新闻"）\n2. 分析持仓表现（如"我的收益归因"）\n3. 评估风险状况（如"分析回撤风险"）\n\n我会智能路由到最合适的专业 Agent 为您服务。',
  followUps: ['📊 查看市场动态', '💼 分析持仓结构', '🛡️ 评估持仓风险'],
  agent: '🤖 Router — 智能路由',
  tools: ['classify_intent'],
}
