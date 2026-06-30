export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-dp-canvas rounded-xl
      rounded-tl-sm w-fit">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-dp-muted animate-pulse-dot"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </div>
  )
}