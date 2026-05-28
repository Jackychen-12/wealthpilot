import { useRef, useEffect, type ReactNode } from 'react'

export function PhoneFrame({ children, resetScroll }: { children: ReactNode; resetScroll?: unknown }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0
  }, [resetScroll])

  return (
    <div className="phone">
      <div className="phone-inner" ref={ref}>
        {children}
      </div>
    </div>
  )
}
