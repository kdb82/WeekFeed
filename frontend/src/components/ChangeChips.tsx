import { useState } from 'react'
import { ApiError, api, errorMessage } from '../api'
import type { Batch, Change, UndoConflict } from '../types'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toasts'
import styles from './ChangeChips.module.css'

function changeLabel(c: Change): string {
  return c.action === 'created' ? `added ${c.kind}` : c.new_status ?? 'changed'
}

function chipClass(c: Change): string {
  if (c.action === 'status_changed') return 'chip chip-ok'
  if (c.kind === 'blocker') return 'chip chip-bad'
  if (c.kind === 'todo') return 'chip chip-accent'
  return 'chip'
}

export default function ChangeChips({ batch, onUndone }: { batch: Batch; onUndone: () => void }) {
  const toast = useToast()
  const [conflicts, setConflicts] = useState<UndoConflict[] | null>(null)
  const [busy, setBusy] = useState(false)
  const undone = batch.undone_at !== null

  async function undo(force: boolean) {
    setBusy(true)
    try {
      await api.undo(batch.id, force)
      setConflicts(null)
      onUndone()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'undo_conflict') {
        setConflicts((e.body as { conflicts: UndoConflict[] }).conflicts)
      } else {
        toast(errorMessage(e))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.changes}>
      {batch.changes.map((c, i) => (
        <div key={i} className={undone ? `${styles.change} ${styles.undone}` : styles.change}>
          <span className={chipClass(c)}>{changeLabel(c)}</span>
          <span>{c.text}</span>
        </div>
      ))}
      <div className={styles.actions}>
        {undone ? (
          <span className="muted">Undone</span>
        ) : (
          <button className="btn btn-sm" onClick={() => undo(false)} disabled={busy}>
            Undo
          </button>
        )}
      </div>
      {conflicts && (
        <ConfirmDialog
          title="Some items changed after this batch"
          confirmLabel="Undo anyway"
          danger
          busy={busy}
          onConfirm={() => undo(true)}
          onCancel={() => setConflicts(null)}
        >
          <ul>
            {conflicts.map((c) => (
              <li key={c.item_id}>{c.reason}</li>
            ))}
          </ul>
        </ConfirmDialog>
      )}
    </div>
  )
}
