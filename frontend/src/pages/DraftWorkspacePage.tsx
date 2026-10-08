import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { api, errorMessage } from '../api'
import ChatThread from '../components/ChatThread'
import Composer from '../components/Composer'
import ConfirmDialog from '../components/ConfirmDialog'
import DraftCard from '../components/DraftCard'
import ErrorBox from '../components/ErrorBox'
import LabelPill from '../components/LabelPill'
import SyncChips from '../components/SyncChips'
import { useToast } from '../components/Toasts'
import { dateTime, fromLocalInput, scopeKey, shortDate, toLocalInput } from '../format'
import {
  LABEL_NAMES, LABELS, type Draft, type DraftDetail, type DraftKind, type Label, type Repo, type Scope, type Section,
} from '../types'
import styles from './DraftWorkspacePage.module.css'

export default function DraftWorkspacePage() {
  const { projectId, label } = useParams()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })

  if (projects.isPending) return <main className={styles.main}><p className="muted">Loading…</p></main>
  if (projects.isError) return <main className={styles.main}><ErrorBox error={projects.error} onRetry={() => projects.refetch()} /></main>

  let scope: Scope
  let title: string
  let repos: Repo[]
  if (projectId !== undefined) {
    const p = projects.data.find((x) => x.id === Number(projectId))
    if (!p) return <main className={styles.main}><p>Project not found. <Link to="/">Back to projects</Link></p></main>
    scope = { label: p.label, projectId: p.id }
    title = p.name
    repos = p.repos
  } else {
    if (!LABELS.includes(label as Label)) return <main className={styles.main}><p>Unknown label. <Link to="/">Back to projects</Link></p></main>
    const l = label as Label
    scope = { label: l, projectId: null }
    title = `All ${LABEL_NAMES[l].toLowerCase()} projects`
    repos = projects.data.filter((p) => p.label === l).flatMap((p) => p.repos)
  }
  return <Workspace key={scopeKey(scope)} scope={scope} title={title} repos={repos} />
}

function Workspace({ scope, title, repos }: { scope: Scope; title: string; repos: Repo[] }) {
  const qc = useQueryClient()
  const toast = useToast()
  const key = scopeKey(scope)
  const drafts = useQuery({ queryKey: ['drafts', key], queryFn: () => api.drafts(scope) })
  const [selected, setSelected] = useState<number | null>(null)
  // The history list is in-progress first, then newest saved: the first entry is the default.
  const selectedId = selected ?? drafts.data?.[0]?.id ?? null

  const refreshScope = () => {
    qc.invalidateQueries({ queryKey: ['drafts', key] })
    qc.invalidateQueries({ queryKey: ['items', key] })
    qc.invalidateQueries({ queryKey: ['projects'] })
  }
  const start = useMutation({
    mutationFn: (kind: DraftKind) => api.startDraft(kind, scope),
    onSuccess: (detail) => {
      qc.setQueryData(['draft', detail.draft.id], detail)
      setSelected(detail.draft.id)
      refreshScope()
    },
    onError: (e) => toast(errorMessage(e)),
  })
  const sync = useMutation({
    mutationFn: () => (scope.projectId !== null ? api.sync({ projectId: scope.projectId }) : api.sync({ label: scope.label })),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      const added = r.results.reduce((n, x) => n + x.new_commits, 0)
      toast(added ? `Synced: ${added} new commits` : 'Synced: no new commits')
    },
    onError: (e) => toast(errorMessage(e)),
  })
  const starting = (kind: DraftKind) => start.isPending && start.variables === kind

  return (
    <main className={styles.main}>
      <div className={`muted ${styles.crumbs}`}>
        <Link to="/">Projects</Link> / {LABEL_NAMES[scope.label]}
        {scope.projectId !== null && <> / {title}</>}
      </div>
      <div className={styles.header}>
        <h1>{title}</h1>
        <LabelPill label={scope.label} />
        <span className={styles.paths}>{repos.map((r) => r.path).join(' · ') || 'No repos yet: add them in Settings'}</span>
        <span className={styles.sync}>
          <SyncChips repos={repos} />
          <button className="btn" onClick={() => sync.mutate()} disabled={sync.isPending || repos.length === 0}>
            {sync.isPending ? 'Syncing…' : 'Sync'}
          </button>
        </span>
      </div>
      <div className={styles.columns}>
        <aside className={styles.left} aria-label="Drafts">
          <button className="btn btn-primary" onClick={() => start.mutate('standup')} disabled={start.isPending}>
            {starting('standup') ? 'Drafting…' : 'New standup'}
          </button>
          <button className="btn" onClick={() => start.mutate('weekly')} disabled={start.isPending}>
            {starting('weekly') ? 'Drafting…' : 'New weekly update'}
          </button>
          <h2 className={`side-heading ${styles.histHead}`}>History</h2>
          {drafts.isError && <ErrorBox error={drafts.error} onRetry={() => drafts.refetch()} />}
          {drafts.data?.length === 0 && <p className="muted">No drafts yet.</p>}
          {drafts.data?.map((d) => (
            <button key={d.id} className={d.id === selectedId ? `${styles.hist} ${styles.histOn}` : styles.hist} onClick={() => setSelected(d.id)}>
              <span className={styles.histTitle}>
                {d.kind === 'standup' ? 'Standup' : 'Weekly update'}
                {d.status === 'in_progress' && ' · in progress'}
              </span>
              <span className="muted">{shortDate(d.saved_at ?? d.created_at)}</span>
            </button>
          ))}
        </aside>
        <section className={styles.center}>
          {selectedId === null ? (
            <div className={styles.empty}>
              <p>No drafts for {title} yet.</p>
              <button className="btn btn-primary" onClick={() => start.mutate('standup')} disabled={start.isPending}>
                {starting('standup') ? 'Drafting…' : 'Start a standup'}
              </button>
            </div>
          ) : (
            <DraftView
              key={selectedId}
              draftId={selectedId}
              onChanged={refreshScope}
              onDiscarded={() => {
                setSelected(null)
                refreshScope()
              }}
            />
          )}
        </section>
        <OpenItemsPanel scope={scope} />
      </div>
    </main>
  )
}

function DraftView({ draftId, onChanged, onDiscarded }: { draftId: number; onChanged: () => void; onDiscarded: () => void }) {
  const detail = useQuery({ queryKey: ['draft', draftId], queryFn: () => api.draft(draftId) })
  if (detail.isPending) return <p className="muted">Loading draft…</p>
  if (detail.isError) return <ErrorBox error={detail.error} onRetry={() => detail.refetch()} />
  if (detail.data.draft.status === 'saved') return <SavedDraft draft={detail.data.draft} />
  return <InProgressDraft detail={detail.data} onChanged={onChanged} onDiscarded={onDiscarded} />
}

function InProgressDraft({ detail, onChanged, onDiscarded }: { detail: DraftDetail; onChanged: () => void; onDiscarded: () => void }) {
  const { draft, messages, stats } = detail
  const qc = useQueryClient()
  const toast = useToast()
  const [wantDiscord, setWantDiscord] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [rangeOpen, setRangeOpen] = useState(false)
  const onError = (e: unknown) => toast(errorMessage(e))

  const discord = useQuery({ queryKey: ['discord', draft.id], queryFn: () => api.discord(draft.id), enabled: wantDiscord })
  const refreshDraft = (fresh?: DraftDetail) => {
    if (fresh) qc.setQueryData(['draft', draft.id], fresh)
    else qc.invalidateQueries({ queryKey: ['draft', draft.id] })
    qc.invalidateQueries({ queryKey: ['discord', draft.id] })
    onChanged()
  }

  const send = useMutation({
    mutationFn: (text: string) => api.sendMessage(draft.id, text),
    onSuccess: () => refreshDraft(),
    onError: (e) => {
      onError(e)
      qc.invalidateQueries({ queryKey: ['draft', draft.id] }) // the message itself was saved; show it with Retry
    },
  })
  const retry = useMutation({ mutationFn: () => api.retry(draft.id), onSuccess: () => refreshDraft(), onError })
  const autosave = useMutation({
    mutationFn: (sections: Section[]) => api.saveSections(draft.id, sections),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['discord', draft.id] }),
    onError,
  })
  const save = useMutation({
    mutationFn: async (sections: Section[]) => {
      await api.saveSections(draft.id, sections)
      return api.saveDraft(draft.id)
    },
    onSuccess: (fresh) => {
      qc.setQueryData(['draft', draft.id], fresh)
      onChanged()
      toast('Saved to history')
    },
    onError,
  })
  const discard = useMutation({
    mutationFn: () => api.discardDraft(draft.id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ['draft', draft.id] })
      onDiscarded()
    },
    onError,
  })
  const changeRange = useMutation({
    mutationFn: ({ start, end }: { start: string; end: string }) => api.changeRange(draft.id, start, end),
    onSuccess: (fresh) => {
      refreshDraft(fresh)
      setRangeOpen(false)
    },
    onError,
  })

  const busy = send.isPending || retry.isPending || changeRange.isPending || save.isPending
  const last = messages[messages.length - 1]
  const unanswered = last?.role === 'user' && !send.isPending && !retry.isPending

  return (
    <div className={styles.draft}>
      <div className={styles.range}>
        <span>
          {dateTime(draft.period_start)} → {dateTime(draft.period_end)} · {stats.commits} commits · {stats.closed} closed · {stats.notes} notes
        </span>
        <button className="btn btn-sm" onClick={() => setRangeOpen((o) => !o)}>Change range</button>
      </div>
      {rangeOpen && (
        <RangeForm draft={draft} busy={changeRange.isPending} onCancel={() => setRangeOpen(false)} onSubmit={(start, end) => changeRange.mutate({ start, end })} />
      )}
      <ChatThread messages={messages} pendingText={send.isPending ? send.variables : undefined} onBatchUndone={() => refreshDraft()} />
      {unanswered && (
        <div className="error-box">
          <span>No reply yet for your last message.</span>
          <button className="btn btn-sm" onClick={() => retry.mutate()}>Retry</button>
        </div>
      )}
      {retry.isPending && <p className="muted">Thinking…</p>}
      <DraftCard
        draft={draft}
        busy={busy}
        discord={discord.data}
        discordLoading={discord.isFetching}
        onShowDiscord={() => setWantDiscord(true)}
        onSections={(sections) => autosave.mutate(sections)}
        onSave={(sections) => save.mutate(sections)}
        onDiscard={() => setConfirmDiscard(true)}
      />
      {discord.isError && <ErrorBox error={discord.error} onRetry={() => discord.refetch()} />}
      <Composer
        placeholder="Tell me about today, or ask for changes (“make it shorter”)…"
        disabled={busy}
        onSend={(text) => send.mutate(text)}
      />
      {confirmDiscard && (
        <ConfirmDialog
          title="Discard this draft?"
          confirmLabel="Discard"
          danger
          busy={discard.isPending}
          onConfirm={() => discard.mutate()}
          onCancel={() => setConfirmDiscard(false)}
        >
          The draft and its chat are deleted. Todos, blockers and notes the agent changed stay as they are.
        </ConfirmDialog>
      )}
    </div>
  )
}

function RangeForm({ draft, busy, onSubmit, onCancel }: {
  draft: Draft; busy: boolean; onSubmit: (start: string, end: string) => void; onCancel: () => void
}) {
  const [start, setStart] = useState(toLocalInput(draft.period_start))
  const [end, setEnd] = useState(toLocalInput(draft.period_end))
  return (
    <form
      className={styles.rangeForm}
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(fromLocalInput(start), fromLocalInput(end))
      }}
    >
      <label>From <input type="datetime-local" className="input" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
      <label>To <input type="datetime-local" className="input" value={end} onChange={(e) => setEnd(e.target.value)} required /></label>
      <button className="btn btn-primary" disabled={busy || !start || !end || start >= end}>{busy ? 'Regenerating…' : 'Regenerate'}</button>
      <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
    </form>
  )
}

function SavedDraft({ draft }: { draft: Draft }) {
  const toast = useToast()
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast('Copied')
    } catch {
      toast('Copy failed: select the text and copy it manually')
    }
  }
  return (
    <div className={styles.draft}>
      <div className={styles.savedHead}>
        <h2>{draft.kind === 'standup' ? 'Standup' : 'Weekly update'} · {shortDate(draft.saved_at ?? draft.created_at)}</h2>
        <span className="muted mono">{dateTime(draft.period_start)} → {dateTime(draft.period_end)}</span>
      </div>
      <div className={styles.panes}>
        {([['Record', draft.record_text], ['Discord', draft.discord_text]] as const).map(([name, text]) => (
          <div key={name} className={styles.pane}>
            <div className={styles.paneHead}>
              <strong>{name}</strong>
              <button className="btn btn-sm" onClick={() => copy(text ?? '')}>Copy</button>
            </div>
            <pre className="pre">{text}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}

function OpenItemsPanel({ scope }: { scope: Scope }) {
  const items = useQuery({ queryKey: ['items', scopeKey(scope)], queryFn: () => api.items(scope) })
  return (
    <aside className={styles.right} aria-label="Open items">
      {items.isError && <ErrorBox error={items.error} onRetry={() => items.refetch()} />}
      {items.data && (
        <>
          {([['Todos', items.data.todos, 'None open'], ['Blockers', items.data.blockers, 'None open'], ['Recent notes', items.data.notes, 'No notes yet']] as const).map(
            ([heading, list, empty]) => (
              <div key={heading} className={styles.itemGroup}>
                <h2 className="side-heading">{heading}</h2>
                {list.length === 0 && <span className="muted">{empty}</span>}
                {list.map((i) => (
                  <span key={i.id} className={styles.item}>
                    {i.text}
                    {scope.projectId === null && i.project_name && <span className="muted"> · {i.project_name}</span>}
                  </span>
                ))}
              </div>
            ),
          )}
          <p className="muted" style={{ fontSize: 12 }}>Change these by telling the agent.</p>
        </>
      )}
    </aside>
  )
}
