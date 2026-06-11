export function Skeleton({ width, height, style }: {
  width?: string | number
  height?: string | number
  style?: React.CSSProperties
}) {
  return <div className="skeleton" style={{ width, height, ...style }} />
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton skeleton-text"
          style={{ width: i === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  )
}
