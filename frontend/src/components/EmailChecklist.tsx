import { useState } from 'react'
import type { EmailCandidate, SettingsData } from '../types'
import styles from './EmailChecklist.module.css'

interface Props {
  candidates: EmailCandidate[]
  username: string
  saving?: boolean
  onSave: (data: SettingsData) => void
}

export default function EmailChecklist({ candidates, username, saving, onSave }: Props) {
  const [name, setName] = useState(username)
  const [checked, setChecked] = useState<Set<string>>(() => new Set(candidates.filter((c) => c.checked).map((c) => c.email)))

  function toggle(email: string) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(email)) next.delete(email)
      else next.add(email)
      return next
    })
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.username}>
        <label htmlFor="github-username">GitHub username</label>
        <input id="github-username" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. kdb82" />
        <span className="muted">Used to suggest your GitHub private email. Rescan after changing it.</span>
      </div>
      {candidates.length === 0 ? (
        <p className="muted">Add a repo in the Repos section to see commit authors here.</p>
      ) : (
        <ul className={styles.list}>
          {candidates.map((c) => (
            <li key={c.email} className={styles.row}>
              <input type="checkbox" id={`email-${c.email}`} checked={checked.has(c.email)} onChange={() => toggle(c.email)} />
              <label htmlFor={`email-${c.email}`} className={styles.email}>{c.email}</label>
              {c.reasons.map((r) => (
                <span key={r} className="chip">{r}</span>
              ))}
              {c.is_new && <span className="chip chip-accent">new · looks like you</span>}
              <span className="muted">{c.commit_count} commits</span>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.actions}>
        <button
          className="btn btn-primary"
          disabled={saving}
          onClick={() => onSave({ github_username: name, my_emails: candidates.map((c) => c.email).filter((e) => checked.has(e)) })}
        >
          Save emails
        </button>
      </div>
    </div>
  )
}
