import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { AiBubble, UserBubble } from '../components/ChatBubble'
import { QuickPills } from '../components/QuickPills'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { chatMessages, chatQuickReplies } from '../data/mock'

export function Chat({ go }: { go: (k: string) => void }) {
  return (
    <div className="screen">
      <Notch />
      <NavBar title="Pilot AI · 持仓追问" onBack={() => go('overview')} />
      <div className="content">
        <div style={{ textAlign: 'center', fontSize: 12, color: colors.textMuted, margin: '8px 0 18px' }}>
          基于您的持仓复盘结果，可以继续追问
        </div>

        {chatMessages.map((msg, i) => {
          if (msg.role === 'user') {
            return <UserBubble key={i}>{msg.content}</UserBubble>
          }

          if (msg.content === 'analysis' && msg.sections) {
            return (
              <AiBubble key={i}>
                <div>这个问题涉及投资决策，我无法直接给出买卖建议。但可以提供几个观察角度供您参考：</div>
                {msg.sections.map((section, j) => (
                  <div key={j} style={{ marginTop: 12 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{section.title}</div>
                    <div style={{ color: colors.textSecondary }}>{section.text}</div>
                  </div>
                ))}
              </AiBubble>
            )
          }

          if (msg.content === 'table' && msg.tableData) {
            return (
              <AiBubble key={i}>
                <div>{msg.intro}</div>
                <div className="data-table">
                  {msg.tableData.map((row, j) => (
                    <div key={j} className="data-row">
                      <span>{row.name}</span>
                      <span
                        style={{
                          fontWeight: 600,
                          color: row.highlight ? colors.primary : colors.text,
                          fontFamily: 'DM Sans',
                        }}
                      >
                        {row.value}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 10, color: colors.textSecondary }}>{msg.conclusion}</div>
              </AiBubble>
            )
          }

          return (
            <AiBubble key={i}>
              {msg.content}
            </AiBubble>
          )
        })}

        <QuickPills items={chatQuickReplies} />
        <FollowUpBar />
        <Disclaimer />
      </div>
    </div>
  )
}
