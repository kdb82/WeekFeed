import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
import { api } from '../api'
import styles from './Layout.module.css'

function readDismissed(): string[] {
  try {
    return JSON.parse(sessionStorage.getItem('dismissed-banners') ?? '[]')
  } catch {
    return []
  }
}

export default function Layout() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const [dismissed, setDismissed] = useState<string[]>(readDismissed)

  const dismiss = (id: string) => {
    const next = [...dismissed, id]
    setDismissed(next)
    try {
      sessionStorage.setItem('dismissed-banners', JSON.stringify(next))
    } catch {
      // storage unavailable: dismissal lasts until reload
    }
  }

  const banners: { id: string; content: ReactNode }[] = []
  if (health.data && !health.data.api_key_loaded) {
    banners.push({ id: 'ai', content: <>AI features are off: add <code>OPENAI_API_KEY</code> and <code>OPENAI_MODEL</code> to <code>.env</code>, then restart.</> })
  }
  if (health.data && !health.data.git_available) {
    banners.push({ id: 'git', content: <>git wasn't found on your PATH, so repos can't be synced.</> })
  }
  if (settings.data && settings.data.my_emails.length === 0) {
    banners.push({ id: 'emails', content: <><Link to="/settings">Confirm your commit emails in Settings</Link> so drafts include your commits.</> })
  }

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>WeekFeed</div>
        <nav className={styles.nav} aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}>
            Projects
          </NavLink>
          <NavLink to="/ask" className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}>
            Ask
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}>
            Settings
          </NavLink>
        </nav>
      </header>
      {banners
        .filter((b) => !dismissed.includes(b.id))
        .map((b) => (
          <div key={b.id} className={styles.banner} role="note">
            <span>{b.content}</span>
            <button className="btn btn-sm btn-ghost" onClick={() => dismiss(b.id)} aria-label="Dismiss">
              Dismiss
            </button>
          </div>
        ))}
      <Outlet />
    </div>
  )
}
