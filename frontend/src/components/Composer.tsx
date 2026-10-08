import { useState } from 'react'
import styles from './Composer.module.css'

interface Props {
  placeholder: string
  disabled?: boolean
  onSend: (text: string) => void
}

/** Enter sends, Shift+Enter adds a newline. */
export default function Composer({ placeholder, disabled, onSend }: Props) {
  const [text, setText] = useState('')

  function send() {
    const value = text.trim()
    if (!value || disabled) return
    onSend(value)
    setText('')
  }

  return (
    <div className={styles.composer}>
      <label htmlFor="composer" className="sr-only">Message</label>
      <textarea
        id="composer"
        rows={2}
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            send()
          }
        }}
      />
      <button className="btn btn-primary" onClick={send} disabled={disabled || !text.trim()}>
        Send
      </button>
    </div>
  )
}
