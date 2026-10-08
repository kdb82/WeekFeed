// Mirrors backend/src/weekfeed/api/serialize.py.

export type Label = 'work' | 'school' | 'personal'
export const LABELS: Label[] = ['work', 'school', 'personal']
export const LABEL_NAMES: Record<Label, string> = { work: 'Work', school: 'School', personal: 'Personal' }

export interface Scope {
  label: Label
  projectId: number | null
}

export interface Repo {
  id: number
  project_id: number
  path: string
  display_name: string
  last_fetched_at: string | null
  last_fetch_error: string | null
}

export interface ProjectCard {
  id: number
  name: string
  label: Label
  repos: Repo[]
  open_todos: number
  open_blockers: number
  last_standup_at: string | null
  oldest_fetch_at: string | null
}

export type ItemKind = 'note' | 'todo' | 'blocker'

export interface Item {
  id: number
  label: Label
  project_id: number | null
  project_name: string | null
  kind: ItemKind
  text: string
  status: 'open' | 'done' | 'resolved'
  created_at: string
  closed_at: string | null
}

export interface Section {
  title: string
  text: string
}

export type DraftKind = 'standup' | 'weekly'

export interface Draft {
  id: number
  kind: DraftKind
  label: Label
  project_id: number | null
  period_start: string
  period_end: string
  status: 'in_progress' | 'saved'
  sections: Section[]
  record_text: string | null
  discord_text: string | null
  created_at: string
  saved_at: string | null
}

export interface Change {
  action: 'created' | 'status_changed'
  kind: ItemKind
  text: string
  new_status: string | null
}

export interface Batch {
  id: number
  undone_at: string | null
  changes: Change[]
}

export interface DraftMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  draft_snapshot: Section[] | null
  batch: Batch | null
  created_at: string
}

export interface DraftDetail {
  draft: Draft
  messages: DraftMessage[]
  stats: { commits: number; closed: number; notes: number }
}

export interface ItemsPanel {
  todos: Item[]
  blockers: Item[]
  notes: Item[]
}

export interface Citation {
  n: number
  source_type: 'item' | 'commit'
  source_id: number
  title: string
  meta: string
  body: string
  label: Label
  project_id: number | null
}

export interface AskResponse {
  answer: string
  terms: string[]
  citations: Citation[]
  batch: Batch | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Health {
  api_key_loaded: boolean
  model: string | null
  git_available: boolean
}

export interface SettingsData {
  github_username: string
  my_emails: string[]
}

export interface EmailCandidate {
  email: string
  commit_count: number
  reasons: string[]
  checked: boolean
  is_new: boolean
}

export interface SyncResult {
  repo_id: number
  fetched: boolean
  error: string | null
  new_commits: number
}

export interface UndoConflict {
  item_id: number
  text: string
  reason: string
}
