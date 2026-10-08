import { act, fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../test/render'
import type { Draft } from '../types'
import DraftCard from './DraftCard'

const draft: Draft = {
  id: 7, kind: 'standup', label: 'work', project_id: 1,
  period_start: '2026-10-06T15:12:00.000000+00:00', period_end: '2026-10-07T15:05:00.000000+00:00',
  status: 'in_progress',
  sections: [
    { title: 'Yesterday', text: '- Fixed login' },
    { title: 'Today', text: '- Review PR' },
    { title: 'Blockers', text: 'None' },
  ],
  record_text: null, discord_text: null, created_at: '', saved_at: null,
}

function setup(overrides: Partial<Parameters<typeof DraftCard>[0]> = {}) {
  const props = {
    draft, onShowDiscord: vi.fn(), onSections: vi.fn(), onSave: vi.fn(), onDiscard: vi.fn(), ...overrides,
  }
  renderWithProviders(<DraftCard {...props} />)
  return props
}

afterEach(() => vi.useRealTimers())

test('shows one editable textarea per section', () => {
  setup()
  expect(screen.getByLabelText('Yesterday')).toHaveValue('- Fixed login')
  expect(screen.getByLabelText('Today')).toHaveValue('- Review PR')
  expect(screen.getByLabelText('Blockers')).toHaveValue('None')
})

test('edits autosave once after a pause', () => {
  vi.useFakeTimers()
  const props = setup()
  fireEvent.change(screen.getByLabelText('Today'), { target: { value: '- Review PR\n- Pair' } })
  fireEvent.change(screen.getByLabelText('Today'), { target: { value: '- Review PR\n- Pair with Sam' } })
  expect(props.onSections).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(800))
  expect(props.onSections).toHaveBeenCalledTimes(1)
  expect(props.onSections).toHaveBeenCalledWith([
    { title: 'Yesterday', text: '- Fixed login' },
    { title: 'Today', text: '- Review PR\n- Pair with Sam' },
    { title: 'Blockers', text: 'None' },
  ])
})

test('the Discord tab requests the Discord text and shows a counter', () => {
  const props = setup({ discord: { text: '**Standup**\n- x', over_limit: false } })
  fireEvent.click(screen.getByRole('tab', { name: 'Discord' }))
  expect(props.onShowDiscord).toHaveBeenCalled()
  expect(screen.getByText(/\*\*Standup\*\*/)).toBeInTheDocument()
  const counter = screen.getByText('15 / 2,000')
  expect(counter).toHaveAttribute('data-over', 'false')
})

test('the counter is flagged when over the Discord limit', () => {
  setup({ discord: { text: 'x'.repeat(2001), over_limit: true } })
  fireEvent.click(screen.getByRole('tab', { name: 'Discord' }))
  expect(screen.getByText('2,001 / 2,000')).toHaveAttribute('data-over', 'true')
})

test('Copy copies the active tab', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  setup({ discord: { text: 'discord text', over_limit: false } })
  fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
  expect(writeText).toHaveBeenLastCalledWith('Yesterday\n- Fixed login\n\nToday\n- Review PR\n\nBlockers\nNone')
  fireEvent.click(screen.getByRole('tab', { name: 'Discord' }))
  fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
  expect(writeText).toHaveBeenLastCalledWith('discord text')
})

test('save and discard call back', () => {
  const props = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Save standup' }))
  expect(props.onSave).toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
  expect(props.onDiscard).toHaveBeenCalled()
})

test('Save sends unsaved edits immediately instead of waiting for autosave', () => {
  vi.useFakeTimers()
  const props = setup()
  fireEvent.change(screen.getByLabelText('Blockers'), { target: { value: '- DB access' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save standup' }))
  expect(props.onSave).toHaveBeenCalledWith([
    { title: 'Yesterday', text: '- Fixed login' },
    { title: 'Today', text: '- Review PR' },
    { title: 'Blockers', text: '- DB access' },
  ])
  act(() => vi.advanceTimersByTime(800))
  expect(props.onSections).not.toHaveBeenCalled()
})
