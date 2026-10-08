import type { ReactNode } from 'react'
import styles from './ConfirmDialog.module.css'

interface Props {
  title: string
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
  children?: ReactNode
}

export default function ConfirmDialog({ title, confirmLabel, danger, busy, onConfirm, onCancel, children }: Props) {
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
      >
        <h2 id="confirm-title" className={styles.title}>{title}</h2>
        {children && <div className={styles.body}>{children}</div>}
        <div className={styles.actions}>
          <button className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm} disabled={busy} autoFocus>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
