import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../test/render'
import type { EmailCandidate } from '../types'
import EmailChecklist from './EmailChecklist'

const candidates: EmailCandidate[] = [
  { email: 'me@personal.com', commit_count: 214, reasons: ['your git config'], checked: true, is_new: false },
  { email: 'new@personal.com', commit_count: 3, reasons: ['your git config'], checked: false, is_new: true },
  { email: 'sam@company.com', commit_count: 98, reasons: [], checked: false, is_new: false },
]

test('shows counts, reasons and the new chip with saved checks', () => {
  renderWithProviders(<EmailChecklist candidates={candidates} username="kdb82" onSave={vi.fn()} />)
  expect(screen.getByLabelText('me@personal.com')).toBeChecked()
  expect(screen.getByLabelText('new@personal.com')).not.toBeChecked()
  expect(screen.getByText('new · looks like you')).toBeInTheDocument()
  expect(screen.getByText('214 commits')).toBeInTheDocument()
  expect(screen.getAllByText('your git config')).toHaveLength(2)
})

test('Save sends the username and every checked email', () => {
  const onSave = vi.fn()
  renderWithProviders(<EmailChecklist candidates={candidates} username="kdb82" onSave={onSave} />)
  fireEvent.click(screen.getByLabelText('new@personal.com'))
  fireEvent.change(screen.getByLabelText('GitHub username'), { target: { value: 'kdb83' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save emails' }))
  expect(onSave).toHaveBeenCalledWith({ github_username: 'kdb83', my_emails: ['me@personal.com', 'new@personal.com'] })
})

test('shows an empty state before any repo is added', () => {
  renderWithProviders(<EmailChecklist candidates={[]} username="" onSave={vi.fn()} />)
  expect(screen.getByText(/Add a repo/)).toBeInTheDocument()
})
