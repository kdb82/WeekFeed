import type {
  AskResponse, Batch, ChatMessage, Draft, DraftDetail, DraftKind, DraftMessage, EmailCandidate, Health, Item,
  ItemsPanel, Label, ProjectCard, Repo, Scope, Section, SettingsData, SyncResult,
} from './types'

/** Error from the backend's uniform {"error", "message"} body. */
export class ApiError extends Error {
  status: number
  code: string
  body: unknown

  constructor(status: number, code: string, message: string, body: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.body = body
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    throw new ApiError(res.status, data?.error ?? 'error', data?.message ?? data?.detail ?? res.statusText, data)
  }
  return data as T
}

const scopeQuery = (s: Scope) => (s.projectId !== null ? `project_id=${s.projectId}` : `label=${s.label}`)

type TurnResponse = { message: DraftMessage; draft: Draft }

export const api = {
  health: () => request<Health>('GET', '/health'),

  projects: () => request<{ projects: ProjectCard[] }>('GET', '/projects').then((r) => r.projects),
  createProject: (name: string, label: Label) => request<ProjectCard>('POST', '/projects', { name, label }),
  updateProject: (id: number, patch: { name?: string; label?: Label }) =>
    request<ProjectCard>('PATCH', `/projects/${id}`, patch),
  deleteProject: (id: number, confirmName: string) =>
    request<null>('DELETE', `/projects/${id}?confirm_name=${encodeURIComponent(confirmName)}`),

  addRepo: (path: string, projectId: number) => request<Repo>('POST', '/repos', { path, project_id: projectId }),
  removeRepo: (id: number) => request<null>('DELETE', `/repos/${id}`),
  sync: (opts: { projectId?: number; label?: Label; force?: boolean } = {}) =>
    request<{ results: SyncResult[] }>('POST', '/sync', {
      project_id: opts.projectId ?? null, label: opts.label ?? null, force: opts.force ?? true,
    }),

  drafts: (s: Scope) => request<{ drafts: Draft[] }>('GET', `/drafts?${scopeQuery(s)}`).then((r) => r.drafts),
  startDraft: (kind: DraftKind, s: Scope) =>
    request<DraftDetail>('POST', '/drafts', { kind, label: s.label, project_id: s.projectId }),
  draft: (id: number) => request<DraftDetail>('GET', `/drafts/${id}`),
  saveSections: (id: number, sections: Section[]) => request<DraftDetail>('PATCH', `/drafts/${id}`, { sections }),
  changeRange: (id: number, start: string, end: string) =>
    request<DraftDetail>('PATCH', `/drafts/${id}`, { period_start: start, period_end: end }),
  sendMessage: (id: number, content: string) => request<TurnResponse>('POST', `/drafts/${id}/messages`, { content }),
  retry: (id: number) => request<TurnResponse>('POST', `/drafts/${id}/retry`),
  discord: (id: number) => request<{ text: string; over_limit: boolean }>('GET', `/drafts/${id}/discord`),
  saveDraft: (id: number) => request<DraftDetail>('POST', `/drafts/${id}/save`),
  discardDraft: (id: number) => request<null>('DELETE', `/drafts/${id}`),

  items: (s: Scope) => request<ItemsPanel>('GET', `/items?${scopeQuery(s)}`),
  saveNote: (text: string, label: Label, projectId: number | null) =>
    request<{ item: Item; batch: Batch }>('POST', '/notes', { text, label, project_id: projectId }),
  undo: (batchId: number, force = false) =>
    request<{ reverted: number; already_gone: number[]; batch: Batch }>('POST', `/batches/${batchId}/undo`, { force }),

  ask: (messages: ChatMessage[]) => request<AskResponse>('POST', '/ask', { messages }),

  settings: () => request<SettingsData>('GET', '/settings'),
  saveSettings: (data: SettingsData) => request<SettingsData>('PUT', '/settings', data),
  emails: () => request<{ emails: EmailCandidate[] }>('GET', '/settings/emails').then((r) => r.emails),
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
