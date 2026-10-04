import type React from 'react'
import { Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { research } from '../api/researchStore'
import { Button } from './kit'

/** 把当前页面的话题带去 AI 研究：功能页给数，AI 研究给解读。 */
export const AskAi: React.FC<{ question: string; label?: string }> = ({ question, label = '让 AI 解读' }) => {
  const navigate = useNavigate()
  return (
    <Button size="sm" variant="secondary" disabled={research.busy}
      onClick={() => { void research.ask(question); navigate('/') }}>
      <Sparkles className="h-3.5 w-3.5" />{label}
    </Button>
  )
}
