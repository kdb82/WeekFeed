import type { DraftMessage } from '../types'
import ChangeChips from './ChangeChips'
import styles from './ChatThread.module.css'

interface Props {
  messages: DraftMessage[]
  pendingText?: string
  onBatchUndone: () => void
}

export default function ChatThread({ messages, pendingText, onBatchUndone }: Props) {
  const snapshotIds = messages.filter((m) => m.draft_snapshot).map((m) => m.id)
  return (
    <div className={styles.thread}>
      {messages.map((m) =>
        m.role === 'user' ? (
          <div key={m.id} className={styles.me}>{m.content}</div>
        ) : (
          <div key={m.id} className={styles.agent}>
            <div className={styles.text}>{m.content}</div>
            {m.batch && <ChangeChips batch={m.batch} onUndone={onBatchUndone} />}
            {m.draft_snapshot && (
              <div className={styles.snapshot}>
                Draft v{snapshotIds.indexOf(m.id) + 1}
                {m.id === snapshotIds[snapshotIds.length - 1] ? ' · current, shown below' : ' · replaced'}
              </div>
            )}
          </div>
        ),
      )}
      {pendingText && (
        <>
          <div className={styles.me}>{pendingText}</div>
          <div className={`${styles.agent} muted`} aria-live="polite">Thinking…</div>
        </>
      )}
    </div>
  )
}
