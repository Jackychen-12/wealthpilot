import { useRef, useEffect, useState, type ReactNode } from 'react'

export function PhoneFrame({ children, resetScroll }: { children: ReactNode; resetScroll?: unknown }) {
  const ref = useRef<HTMLDivElement>(null)
  const [dark, setDark] = useState(false)

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0
  }, [resetScroll])

  return (
    <div className={`phone${dark ? ' dark' : ''}`}>
      <div className="dark-toggle" onClick={() => setDark(!dark)}>
        {dark ? '☀️' : '🌙'}
      </div>
      <div className="phone-inner" ref={ref}>
        {children}
      </div>
    </div>
  )
}
