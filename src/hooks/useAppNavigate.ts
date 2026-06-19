import { useNavigate } from 'react-router-dom'
import type { ScreenKey } from '../types'

const SCREEN_TO_PATH: Record<ScreenKey, string> = {
  home: '/',
  portfolio: '/portfolio',
  overview: '/overview',
  attribution: '/attribution',
  drawdown: '/drawdown',
  health: '/health',
  suggest: '/suggestions',
  weekly: '/weekly',
  chat: '/chat',
  login: '/login',
  'risk-profile': '/risk-profile',
}

export function useAppNavigate() {
  const navigate = useNavigate()
  return (screen: ScreenKey) => {
    navigate(SCREEN_TO_PATH[screen] ?? '/')
  }
}
