export function FollowUpBar({ placeholder }: { placeholder?: string }) {
  return (
    <div className="follow-bar">
      <span>{placeholder || '继续追问...'}</span>
      <span className="send">&#10148;</span>
    </div>
  )
}
