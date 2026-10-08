import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, errorMessage } from '../api'
import ConfirmDialog from '../components/ConfirmDialog'
import EmailChecklist from '../components/EmailChecklist'
import ErrorBox from '../components/ErrorBox'
import LabelPill from '../components/LabelPill'
import { syncLabel } from '../components/SyncChips'
import { useToast } from '../components/Toasts'
import { LABEL_NAMES, LABELS, type Label, type ProjectCard } from '../types'
import styles from './SettingsPage.module.css'

export default function SettingsPage() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  return (
    <main className={styles.main}>
      <h1>Settings</h1>
      {projects.isError && <ErrorBox error={projects.error} onRetry={() => projects.refetch()} />}
      <ProjectsSection projects={projects.data ?? []} />
      <ReposSection projects={projects.data ?? []} />
      <EmailsSection />
      <AiSection />
    </main>
  )
}

function useInvalidateAll() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['projects'] })
    qc.invalidateQueries({ queryKey: ['emails'] })
    qc.invalidateQueries({ queryKey: ['drafts'] })
    qc.invalidateQueries({ queryKey: ['items'] })
  }
}

function ProjectsSection({ projects }: { projects: ProjectCard[] }) {
  const toast = useToast()
  const invalidate = useInvalidateAll()
  const [name, setName] = useState('')
  const [label, setLabel] = useState<Label>('work')
  const create = useMutation({
    mutationFn: () => api.createProject(name.trim(), label),
    onSuccess: () => { setName(''); invalidate() },
    onError: (e) => toast(errorMessage(e)),
  })
  return (
    <section className={styles.card} aria-label="Projects">
      <div className={styles.cardHead}>
        <h2>Projects</h2>
        <span className="muted">Repos and items take their project's label</span>
      </div>
      {projects.length === 0 && <p className="muted">No projects yet.</p>}
      {projects.map((p) => <ProjectRow key={p.id} project={p} />)}
      <form className={styles.addRow} onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate() }}>
        <label htmlFor="new-project" className="sr-only">New project name</label>
        <input id="new-project" className="input" placeholder="New project name" value={name} onChange={(e) => setName(e.target.value)} />
        <label htmlFor="new-project-label" className="sr-only">Label</label>
        <select id="new-project-label" className="input" value={label} onChange={(e) => setLabel(e.target.value as Label)}>
          {LABELS.map((l) => <option key={l} value={l}>{LABEL_NAMES[l]}</option>)}
        </select>
        <button className="btn btn-primary" disabled={!name.trim() || create.isPending}>Add project</button>
      </form>
    </section>
  )
}

function ProjectRow({ project: p }: { project: ProjectCard }) {
  const toast = useToast()
  const invalidate = useInvalidateAll()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(p.name)
  const [deleting, setDeleting] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const onError = (e: unknown) => toast(errorMessage(e))
  const update = useMutation({
    mutationFn: (patch: { name?: string; label?: Label }) => api.updateProject(p.id, patch),
    onSuccess: () => { setRenaming(false); invalidate() },
    onError,
  })
  const remove = useMutation({
    mutationFn: () => api.deleteProject(p.id, confirmName),
    onSuccess: () => { setDeleting(false); invalidate() },
    onError,
  })

  return (
    <div className={styles.row}>
      {renaming ? (
        <form className={styles.inline} onSubmit={(e) => { e.preventDefault(); update.mutate({ name }) }}>
          <label htmlFor={`rename-${p.id}`} className="sr-only">Project name</label>
          <input id={`rename-${p.id}`} className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <button className="btn btn-sm btn-primary" disabled={!name.trim()}>Save</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setRenaming(false)}>Cancel</button>
        </form>
      ) : (
        <strong className={styles.grow}>{p.name}</strong>
      )}
      <LabelPill label={p.label} />
      <span className="muted">{p.repos.length} {p.repos.length === 1 ? 'repo' : 'repos'}</span>
      <span className={styles.rowActions}>
        {!renaming && <button className="btn btn-sm btn-ghost" onClick={() => setRenaming(true)}>Rename</button>}
        <label htmlFor={`label-${p.id}`} className="sr-only">Label for {p.name}</label>
        <select id={`label-${p.id}`} className="input" value={p.label} onChange={(e) => update.mutate({ label: e.target.value as Label })}>
          {LABELS.map((l) => <option key={l} value={l}>{LABEL_NAMES[l]}</option>)}
        </select>
        <button className="btn btn-sm btn-ghost" onClick={() => setDeleting(true)}>Delete</button>
      </span>
      {deleting && (
        <ConfirmDialog
          title={`Delete ${p.name}?`}
          confirmLabel="Delete project"
          danger
          busy={remove.isPending}
          onConfirm={() => remove.mutate()}
          onCancel={() => setDeleting(false)}
        >
          <p>Its repos, synced commits and drafts are deleted. Its notes, todos and blockers stay, without a project.</p>
          <label className={styles.confirmLabel}>
            Type <strong>{p.name}</strong> to confirm
            <input className="input" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} />
          </label>
        </ConfirmDialog>
      )}
    </div>
  )
}

function ReposSection({ projects }: { projects: ProjectCard[] }) {
  const toast = useToast()
  const invalidate = useInvalidateAll()
  const [path, setPath] = useState('')
  const [projectId, setProjectId] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const add = useMutation({
    mutationFn: () => api.addRepo(path.trim(), Number(projectId)),
    onSuccess: () => { setPath(''); setError(null); invalidate() },
    onError: (e) => setError(errorMessage(e)),
  })
  const remove = useMutation({ mutationFn: (id: number) => api.removeRepo(id), onSuccess: invalidate, onError: (e) => toast(errorMessage(e)) })
  const repos = projects.flatMap((p) => p.repos.map((r) => ({ repo: r, project: p })))

  return (
    <section className={styles.card} aria-label="Repos">
      <div className={styles.cardHead}>
        <h2>Repos</h2>
        <span className="muted">Fetched automatically, at most every 15 min</span>
      </div>
      {repos.length === 0 && <p className="muted">No repos yet.</p>}
      {repos.map(({ repo, project }) => (
        <div key={repo.id} className={styles.row}>
          <span className={`mono ${styles.grow} ${styles.path}`}>{repo.path}</span>
          <span className="muted">{project.name}</span>
          <span className={`chip ${repo.last_fetch_error ? 'chip-warn' : 'chip-ok'}`}>{syncLabel(repo)}</span>
          <button className="btn btn-sm btn-ghost" onClick={() => remove.mutate(repo.id)}>Remove</button>
        </div>
      ))}
      <form className={styles.addRow} onSubmit={(e) => { e.preventDefault(); if (path.trim() && projectId !== '') add.mutate() }}>
        <label htmlFor="repo-path" className="sr-only">Repo folder path</label>
        <input id="repo-path" className={`input mono ${styles.grow}`} placeholder="/Users/you/code/my-repo" value={path} onChange={(e) => setPath(e.target.value)} />
        <label htmlFor="repo-project" className="sr-only">Project</label>
        <select id="repo-project" className="input" value={projectId} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : '')}>
          <option value="">Choose project…</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button className="btn btn-primary" disabled={!path.trim() || projectId === '' || add.isPending}>
          {add.isPending ? 'Adding…' : 'Add repo'}
        </button>
      </form>
      {error && <p className={styles.formError} role="alert">{error}</p>}
    </section>
  )
}

function EmailsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const emails = useQuery({ queryKey: ['emails'], queryFn: api.emails })
  const save = useMutation({
    mutationFn: api.saveSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['emails'] })
      toast('Saved')
    },
    onError: (e) => toast(errorMessage(e)),
  })
  return (
    <section className={styles.card} aria-label="My commit emails">
      <div className={styles.cardHead}>
        <h2>My commit emails</h2>
        <button className="btn btn-sm" onClick={() => emails.refetch()} disabled={emails.isFetching}>
          {emails.isFetching ? 'Scanning…' : 'Rescan repos'}
        </button>
      </div>
      <p className="muted">Every author found in your repos. Checked emails count as you.</p>
      {(settings.isError || emails.isError) && <ErrorBox error={settings.error ?? emails.error} />}
      {settings.data && emails.data && (
        <EmailChecklist
          key={JSON.stringify([emails.data, settings.data])}
          candidates={emails.data}
          username={settings.data.github_username}
          saving={save.isPending}
          onSave={(data) => save.mutate(data)}
        />
      )}
    </section>
  )
}

function AiSection() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  return (
    <section className={styles.card} aria-label="AI">
      <h2>AI</h2>
      {health.data && (
        <div className={styles.aiRow}>
          <span>API key <span className={`chip ${health.data.api_key_loaded ? 'chip-ok' : 'chip-warn'}`}>{health.data.api_key_loaded ? 'loaded from .env' : 'missing'}</span></span>
          <span>Model <span className="chip mono">{health.data.model ?? 'not set'}</span></span>
        </div>
      )}
      <p className="muted">Read-only here. Edit <code>.env</code> and restart to change these.</p>
    </section>
  )
}
