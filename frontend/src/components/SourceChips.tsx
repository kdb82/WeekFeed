import { useState } from 'react'
import type { Citation } from '../types'
import styles from './SourceChips.module.css'

export default function SourceChips({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (citations.length === 0) return null
  const current = citations.find((c) => c.n === open)
  return (
    <div className={styles.wrap}>
      <div className={styles.chips}>
        {citations.map((c) => (
          <button
            key={c.n}
            className={open === c.n ? `${styles.chip} ${styles.on}` : styles.chip}
            aria-expanded={open === c.n}
            onClick={() => setOpen(open === c.n ? null : c.n)}
          >
            <span className={styles.n}>{c.n}</span>
            {c.meta}
          </button>
        ))}
      </div>
      {current && (
        <div className={styles.card}>
          <pre className={styles.body}>{current.body}</pre>
        </div>
      )}
    </div>
  )
}
