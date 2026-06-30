import { useState, useRef, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { clsx } from 'clsx'

const SUGGESTIONS = [
  'Summarise key trends',
  'Which columns have anomalies?',
  'Show top 10 rows by revenue',
  'What are the main correlations?',
]

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(true)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    setShowSuggestions(false)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`
  }

  return (
    <div className="border-t border-dp-border p-3">
      {/* Quick suggestions */}
      {showSuggestions && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => { setValue(s); setShowSuggestions(false); textareaRef.current?.focus() }}
              className="text-2xs px-2 py-1 rounded-md bg-dp-canvas border border-dp-border
                text-dp-text-secondary hover:border-dp-violet hover:text-dp-violet
                transition-colors truncate max-w-[160px]"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Ask a question about your data…"
          disabled={disabled}
          rows={1}
          className={clsx(
            'dp-input flex-1 resize-none overflow-hidden leading-relaxed',
            'min-h-[36px] max-h-[120px]',
          )}
        />
        <button
          onClick={handleSend}
          disabled={!value.trim() || disabled}
          className={clsx(
            'w-9 h-9 rounded-md flex items-center justify-center flex-shrink-0 transition-colors',
            value.trim() && !disabled
              ? 'bg-dp-violet text-white hover:bg-dp-violet-light'
              : 'bg-dp-canvas text-dp-muted cursor-not-allowed',
          )}
          aria-label="Send message"
        >
          <Send size={14} />
        </button>
      </div>
      <p className="text-2xs text-dp-muted mt-1.5 text-center">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  )
}