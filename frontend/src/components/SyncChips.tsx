import { relativeTime } from '../format'
import type { Repo } from '../types'

export function syncLabel(r: Repo): string {
  if (r.last_fetch_error) return `${r.display_name}: ${r.last_fetch_error}`
  if (r.last_fetched_at) return `${r.display_name}: synced ${relativeTime(r.last_fetched_at)}`
  return `${r.display_name}: not synced`
}

export default function SyncChips({ repos }: { repos: Repo[] }) {
  return (
    <>
      {repos.map((r) => (
        <span key={r.id} className={`chip ${r.last_fetch_error ? 'chip-warn' : 'chip-ok'}`}>
          {syncLabel(r)}
        </span>
      ))}
    </>
  )
}
