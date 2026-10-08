import { useMutation, useQuery } from '@tanstack/react-query'
import { Fragment, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import ChangeChips from '../components/ChangeChips'
import Composer from '../components/Composer'
import ConfirmDialog from '../components/ConfirmDialog'
import SourceChips from '../components/SourceChips'
import { useToast } from '../components/Toasts'
import { LABEL_NAMES, LABELS, type AskResponse, type Batch, type ChatMessage, type Label } from '../types'
import styles from './AskPage.module.css'

type Turn = { role: 'user'; content: string } | { role: 'assistant'; content: string; response: AskResponse }

export default function AskPage() {
  const toast = useToast()
  const [turns, setTurns] = useState<Turn[]>([])
  const [confirmNew, setConfirmNew] = useState(false)

  // Opening Ask pulls in recent commits in the background (throttled, not forced).
  useEffect(() => {
    api.sync({ force: false }).catch(() => {})
  }, [])

  const ask = useMutation({
    mutationFn: (history: ChatMessage[]) => api.ask(history),
    onSuccess: (r) => setTurns((t) => [...t, { role: 'assistant', content: r.answer, response: r }]),
    onError: (e) => toast(errorMessage(e)),
  })

  const history = (list: Turn[]): ChatMessage[] => list.map(({ role, content }) => ({ role, content }))
  function send(text: string) {
    const next: Turn[] = [...turns, { role: 'user', content: text }]
    setTurns(next)
    ask.mutate(history(next))
  }
  function setBatch(index: number, batch: Batch) {
    setTurns((t) => t.map((turn, i) => (i === index && turn.role === 'assistant' ? { ...turn, response: { ...turn.response, batch } } : turn)))
  }

  const last = turns[turns.length - 1]
  const unanswered = last?.role === 'user' && !ask.isPending

  return (
    <main className={styles.main}>
      <div className={styles.head}>
        <h1>Ask</h1>
        <span className="muted">Searches every project, note and commit</span>
        <button className="btn btn-sm" onClick={() => (turns.length ? setConfirmNew(true) : undefined)} disabled={!turns.length}>
          New chat
        </button>
      </div>
      {turns.length === 0 && (
        <p className="muted">Ask about your own work, like “how did I fix the auth bug?” or “what did I decide about rate limits?”.</p>
      )}
      <div className={styles.thread}>
        {turns.map((t, i) =>
          t.role === 'user' ? (
            <div key={i} className={styles.me}>{t.content}</div>
          ) : (
            <Answer key={i} response={t.response} onBatch={(b) => setBatch(i, b)} />
          ),
        )}
        {ask.isPending && <p className="muted" aria-live="polite">Thinking…</p>}
        {unanswered && (
          <div className="error-box">
            <span>No answer yet.</span>
            <button className="btn btn-sm" onClick={() => ask.mutate(history(turns))}>Retry</button>
          </div>
        )}
      </div>
      <Composer placeholder="Ask about anything you've noted or committed…" disabled={ask.isPending} onSend={send} />
      {confirmNew && (
        <ConfirmDialog
          title="Start a new chat?"
          confirmLabel="New chat"
          onConfirm={() => {
            setTurns([])
            setConfirmNew(false)
          }}
          onCancel={() => setConfirmNew(false)}
        >
          This conversation isn't saved anywhere.
        </ConfirmDialog>
      )}
    </main>
  )
}

function withBadges(text: string) {
  return text.split(/(\[\d+\])/g).map((part, i) =>
    /^\[\d+\]$/.test(part) ? <span key={i} className={styles.cite}>{part.slice(1, -1)}</span> : <Fragment key={i}>{part}</Fragment>,
  )
}

function Answer({ response, onBatch }: { response: AskResponse; onBatch: (b: Batch) => void }) {
  return (
    <div className={styles.answer}>
      {response.terms.length > 0 && (
        <div className={`muted mono ${styles.terms}`}>
          searched: {response.terms.join(' · ')} → {response.citations.length} cited
        </div>
      )}
      <p className={styles.text}>{withBadges(response.answer)}</p>
      <SourceChips citations={response.citations} />
      {response.batch && (
        <ChangeChips batch={response.batch} onUndone={() => onBatch({ ...response.batch!, undone_at: new Date().toISOString() })} />
      )}
      <SaveAsNote response={response} />
    </div>
  )
}

function mostCited(r: AskResponse): { label: Label; projectId: number | null } {
  const counts = new Map<number, number>()
  for (const m of r.answer.matchAll(/\[(\d+)\]/g)) counts.set(Number(m[1]), (counts.get(Number(m[1])) ?? 0) + 1)
  const best = [...r.citations].sort((a, b) => (counts.get(b.n) ?? 0) - (counts.get(a.n) ?? 0))[0]
  return best ? { label: best.label, projectId: best.project_id } : { label: 'work', projectId: null }
}

function SaveAsNote({ response }: { response: AskResponse }) {
  const toast = useToast()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const initial = mostCited(response)
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState<Label>(initial.label)
  const [projectId, setProjectId] = useState<number | null>(initial.projectId)
  const [batch, setBatch] = useState<Batch | null>(null)
  const save = useMutation({
    mutationFn: () => api.saveNote(response.answer, label, projectId),
    onSuccess: (r) => {
      setBatch(r.batch)
      setOpen(false)
    },
    onError: (e) => toast(errorMessage(e)),
  })

  if (batch) return <ChangeChips batch={batch} onUndone={() => setBatch({ ...batch, undone_at: new Date().toISOString() })} />
  if (!open) {
    return (
      <div>
        <button className="btn btn-sm" onClick={() => setOpen(true)}>Save answer as note</button>
      </div>
    )
  }
  const inLabel = (projects.data ?? []).filter((p) => p.label === label)
  return (
    <form className={styles.saveForm} onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <label>
        Label
        <select className="input" value={label} onChange={(e) => { setLabel(e.target.value as Label); setProjectId(null) }}>
          {LABELS.map((l) => <option key={l} value={l}>{LABEL_NAMES[l]}</option>)}
        </select>
      </label>
      <label>
        Project
        <select className="input" value={projectId ?? ''} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">No project</option>
          {inLabel.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <button className="btn btn-primary btn-sm" disabled={save.isPending}>Save note</button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  )
}
