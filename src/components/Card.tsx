import type { ReactNode, CSSProperties } from 'react'

export function Card({
  children,
  onClick,
  className = '',
  style,
}: {
  children: ReactNode
  onClick?: () => void
  className?: string
  style?: CSSProperties
}) {
  return (
    <div
      className={`card ${onClick ? 'card-click' : ''} ${className}`}
      onClick={onClick}
      style={style}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <div className="card-title">{children}</div>
}
