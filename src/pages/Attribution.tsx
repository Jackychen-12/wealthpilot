import { useState } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { BarChart } from '../components/BarChart'
import { AiInsight } from '../components/AiInsight'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { attributionByFund, attributionByIndustry, attributionByAsset } from '../data/mock'

const tabs = ['按基金', '按行业', '按资产类型']
const datasets = [attributionByFund, attributionByIndustry, attributionByAsset]

export function Attribution({ go }: { go: (k: string) => void }) {
  const [tab, setTab] = useState(0)

  return (
    <div className="screen">
      <Notch />
      <NavBar title="收益归因分析" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title">收益归因分析</div>
          <div className="tab-bar">
            {tabs.map((t, i) => (
              <div key={i} className={`tab ${tab === i ? 'on' : ''}`} onClick={() => setTab(i)}>
                {t}
              </div>
            ))}
          </div>
          {datasets[tab].map((d, i) => (
            <BarChart key={`${tab}-${i}`} name={d.name} value={d.value} pct={d.pct} positive={d.positive} />
          ))}
          <AiInsight>
            本周收益主要由半导体板块驱动（占总收益64%），受英伟达财报超预期和国内AI算力政策利好推动。医疗板块受集采政策扩围预期拖累。
          </AiInsight>
        </div>

        <div className="card">
          <div className="card-title">配置效应 vs 选择效应</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <div
              style={{
                flex: 1,
                background: 'linear-gradient(135deg,#EFF6FF,#F8FAFF)',
                borderRadius: 10,
                padding: 14,
                textAlign: 'center',
                border: '1px solid #DBEAFE',
              }}
            >
              <div style={{ fontSize: 11, color: colors.textMuted }}>配置效应</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: colors.primary, marginTop: 2, fontFamily: 'DM Sans' }}>
                +0.89%
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>权益配置偏高获益</div>
            </div>
            <div style={{ flex: 1, background: '#F7F8FA', borderRadius: 10, padding: 14, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: colors.textMuted }}>选择效应</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: colors.danger, marginTop: 2, fontFamily: 'DM Sans' }}>
                +0.53%
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>半导体选基有超额</div>
            </div>
          </div>
          <AiInsight>
            收益一部分来自"买对了方向"（多配了权益少配了债），一部分来自"选对了产品"（半导体基金跑赢同类）。
          </AiInsight>
        </div>
        <FollowUpBar placeholder="针对归因结果继续追问..." />
        <Disclaimer />
      </div>
    </div>
  )
}
