import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, errorMessage } from '../api'
import ErrorBox from '../components/ErrorBox'
import LabelPill from '../components/LabelPill'
import { useToast } from '../components/Toasts'
import { relativeTime, shortDate } from '../format'
import { LABEL_NAMES, LABELS, type Label, type ProjectCard } from '../types'
import styles from './ProjectsPage.module.css'

export default function ProjectsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const syncAll = useMutation({
    mutationFn: () => api.sync(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (e) => toast(errorMessage(e)),
  })

  if (projects.isPending) return <main className={styles.main}><p className="muted">Loading…</p></main>
  if (projects.isError) {
    return <main className={styles.main}><ErrorBox error={projects.error} onRetry={() => projects.refetch()} /></main>
  }

  const fetches = projects.data.flatMap((p) => p.repos.map((r) => r.last_fetched_at)).filter((x): x is string => !!x)
  const lastSync = fetches.length ? fetches.reduce((a, b) => (a > b ? a : b)) : null

  return (
    <main className={styles.main}>
      <div className={styles.head}>
        <h1>Projects</h1>
        <div className={styles.headRight}>
          <span className="muted">{lastSync ? `Last sync ${relativeTime(lastSync)}` : 'Not synced yet'}</span>
          <button className="btn" onClick={() => syncAll.mutate()} disabled={syncAll.isPending}>
            {syncAll.isPending ? 'Syncing…' : 'Sync all'}
          </button>
        </div>
      </div>
      {projects.data.length === 0 && (
        <p className="muted">
          Group your repos into projects. Create one in any column, then add its repo folders in <Link to="/settings">Settings</Link>.
        </p>
      )}
      <div className={styles.board}>
        {LABELS.map((label) => (
          <LabelColumn key={label} label={label} projects={projects.data.filter((p) => p.label === label)} />
        ))}
      </div>
    </main>
  )
}

function LabelColumn({ label, projects }: { label: Label; projects: ProjectCard[] }) {
  return (
    <section className={`${styles.column} ${styles[label]}`} aria-label={LABEL_NAMES[label]}>
      <div className={styles.colHead}>
        <LabelPill label={label} />
        <span className="muted">{projects.length}</span>
        <Link to={`/labels/${label}/draft`} className={styles.labelLink}>
          Standup for all {LABEL_NAMES[label].toLowerCase()}
        </Link>
      </div>
      {projects.map((p) => (
        <ProjectCardView key={p.id} project={p} />
      ))}
      <NewProjectForm label={label} />
    </section>
  )
}

function ProjectCardView({ project: p }: { project: ProjectCard }) {
  const errors = p.repos.filter((r) => r.last_fetch_error)
  return (
    <Link to={`/projects/${p.id}`} className={styles.card}>
      <strong className={styles.cardName}>{p.name}</strong>
      <span className={styles.repos}>{p.repos.length ? p.repos.map((r) => r.display_name).join(' · ') : 'No repos yet'}</span>
      {(p.open_todos > 0 || p.open_blockers > 0 || errors.length > 0) && (
        <span className={styles.chips}>
          {p.open_todos > 0 && <span className="chip">{p.open_todos} {p.open_todos === 1 ? 'todo' : 'todos'}</span>}
          {p.open_blockers > 0 && (
            <span className="chip chip-bad">{p.open_blockers} {p.open_blockers === 1 ? 'blocker' : 'blockers'}</span>
          )}
          {errors.map((r) => (
            <span key={r.id} className="chip chip-warn">{r.display_name}: {r.last_fetch_error}</span>
          ))}
        </span>
      )}
      <span className={styles.foot}>
        <span>{p.last_standup_at ? `Last standup ${shortDate(p.last_standup_at)}` : 'No standups yet'}</span>
        <span>{p.oldest_fetch_at ? `synced ${relativeTime(p.oldest_fetch_at)}` : ''}</span>
      </span>
    </Link>
  )
}

function NewProjectForm({ label }: { label: Label }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const create = useMutation({
    mutationFn: () => api.createProject(name.trim(), label),
    onSuccess: () => {
      setName('')
      setOpen(false)
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (e) => toast(errorMessage(e)),
  })

  if (!open) {
    return (
      <button className={styles.newBtn} onClick={() => setOpen(true)}>
        + New project
      </button>
    )
  }
  return (
    <form
      className={styles.newForm}
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) create.mutate()
      }}
    >
      <label htmlFor={`new-${label}`} className="sr-only">New {LABEL_NAMES[label].toLowerCase()} project name</label>
      <input id={`new-${label}`} className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" />
      <button className="btn btn-primary" disabled={create.isPending || !name.trim()}>Add</button>
      <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  )
}
