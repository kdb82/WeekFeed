import { useEffect, useRef, useState } from 'react'
import type { Draft, Section } from '../types'
import { useToast } from './Toasts'
import styles from './DraftCard.module.css'

const AUTOSAVE_MS = 800
const DISCORD_LIMIT = 2000

export function renderRecord(sections: Section[]): string {
  return sections.map((s) => `${s.title}\n${s.text.trim() || 'None'}`).join('\n\n')
}

interface Props {
  draft: Draft
  discord?: { text: string; over_limit: boolean }
  discordLoading?: boolean
  busy?: boolean
  onShowDiscord: () => void
  onSections: (sections: Section[]) => void
  /** Called with the current text so the caller can persist it before saving. */
  onSave: (sections: Section[]) => void
  onDiscard: () => void
}

export default function DraftCard({ draft, discord, discordLoading, busy, onShowDiscord, onSections, onSave, onDiscard }: Props) {
  const toast = useToast()
  const [tab, setTab] = useState<'record' | 'discord'>('record')
  const [sections, setSections] = useState<Section[]>(draft.sections)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<Section[] | null>(null)
  const onSectionsRef = useRef(onSections)
  onSectionsRef.current = onSections

  // When the server's sections change (agent turn, new range), show them.
  const serverKey = JSON.stringify(draft.sections)
  useEffect(() => {
    setSections(JSON.parse(serverKey))
  }, [serverKey])

  // Flush a pending edit if the card unmounts mid-pause.
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
    if (pending.current) onSectionsRef.current(pending.current)
  }, [])

  function edit(index: number, text: string) {
    const next = sections.map((s, i) => (i === index ? { ...s, text } : s))
    setSections(next)
    pending.current = next
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      pending.current = null
      onSectionsRef.current(next)
    }, AUTOSAVE_MS)
  }

  function cancelPending() {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    const unsaved = pending.current
    pending.current = null
    return unsaved
  }

  function showDiscord() {
    const unsaved = cancelPending()
    if (unsaved) onSectionsRef.current(unsaved)
    setTab('discord')
    onShowDiscord()
  }

  async function copy() {
    const text = tab === 'record' ? renderRecord(sections) : discord?.text ?? ''
    try {
      await navigator.clipboard.writeText(text)
      toast('Copied')
    } catch {
      toast('Copy failed: select the text and copy it manually')
    }
  }

  const discordLength = discord?.text.length ?? 0
  const kindName = draft.kind === 'standup' ? 'standup' : 'weekly update'

  return (
    <section className={styles.card} aria-label="Draft">
      <div className={styles.tabs} role="tablist">
        <button role="tab" aria-selected={tab === 'record'} className={tab === 'record' ? styles.tabOn : styles.tab} onClick={() => setTab('record')}>
          Record
        </button>
        <button role="tab" aria-selected={tab === 'discord'} className={tab === 'discord' ? styles.tabOn : styles.tab} onClick={showDiscord}>
          Discord
        </button>
        {tab === 'discord' && discord && (
          <span className={styles.counter} data-over={String(discordLength > DISCORD_LIMIT)}>
            {discordLength.toLocaleString('en-US')} / 2,000
          </span>
        )}
      </div>
      <div className={styles.body}>
        {tab === 'record' ? (
          sections.map((s, i) => (
            <div key={s.title} className={styles.section}>
              <label htmlFor={`section-${draft.id}-${i}`}>{s.title}</label>
              <textarea
                id={`section-${draft.id}-${i}`}
                className="input"
                rows={Math.max(2, s.text.split('\n').length + 1)}
                value={s.text}
                onChange={(e) => edit(i, e.target.value)}
                disabled={busy}
              />
            </div>
          ))
        ) : discordLoading ? (
          <p className="muted">Writing the Discord version…</p>
        ) : (
          <pre className="pre">{discord?.text ?? ''}</pre>
        )}
        <div className={styles.actions}>
          <button className="btn btn-ghost" onClick={onDiscard} disabled={busy}>
            Discard
          </button>
          <button className="btn" onClick={copy} disabled={tab === 'discord' && !discord}>
            Copy
          </button>
          <button className="btn btn-primary" onClick={() => { cancelPending(); onSave(sections) }} disabled={busy}>
            Save {kindName}
          </button>
        </div>
      </div>
    </section>
  )
}
