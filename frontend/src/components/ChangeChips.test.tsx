import { fireEvent, screen, waitFor } from '@testing-library/react'
import { ApiError, api } from '../api'
import { renderWithProviders } from '../test/render'
import type { Batch } from '../types'
import ChangeChips from './ChangeChips'

const batch: Batch = {
  id: 12,
  undone_at: null,
  changes: [
    { action: 'created', kind: 'todo', text: 'Review PR', new_status: 'open' },
    { action: 'status_changed', kind: 'blocker', text: 'DB access', new_status: 'resolved' },
  ],
}

afterEach(() => vi.restoreAllMocks())

test('lists the changes with readable labels', () => {
  renderWithProviders(<ChangeChips batch={batch} onUndone={vi.fn()} />)
  expect(screen.getByText('added todo')).toBeInTheDocument()
  expect(screen.getByText('Review PR')).toBeInTheDocument()
  expect(screen.getByText('resolved')).toBeInTheDocument()
})

test('Undo reverts the batch and reports back', async () => {
  const undo = vi.spyOn(api, 'undo').mockResolvedValue({ reverted: 2, already_gone: [], draft_restored: true, batch: { ...batch, undone_at: 'x' } })
  const onUndone = vi.fn()
  renderWithProviders(<ChangeChips batch={batch} onUndone={onUndone} />)
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  await waitFor(() => expect(onUndone).toHaveBeenCalled())
  expect(undo).toHaveBeenCalledWith(12, false)
})

test('says so when the draft text changed after the message and was left alone', async () => {
  vi.spyOn(api, 'undo').mockResolvedValue({ reverted: 2, already_gone: [], draft_restored: false, batch: { ...batch, undone_at: 'x' } })
  renderWithProviders(<ChangeChips batch={batch} onUndone={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  expect(await screen.findByText(/draft changed after this message/i)).toBeInTheDocument()
})

test('a conflict opens a dialog and Undo anyway forces it', async () => {
  const conflict = new ApiError(409, 'undo_conflict', '1 item changed', {
    conflicts: [{ item_id: 3, text: 'Review PR', reason: "'Review PR' was changed after this batch" }],
  })
  const undo = vi.spyOn(api, 'undo')
    .mockRejectedValueOnce(conflict)
    .mockResolvedValueOnce({ reverted: 2, already_gone: [], draft_restored: null, batch })
  const onUndone = vi.fn()
  renderWithProviders(<ChangeChips batch={batch} onUndone={onUndone} />)
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  expect(await screen.findByRole('dialog')).toHaveTextContent("'Review PR' was changed after this batch")
  expect(onUndone).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Undo anyway' }))
  await waitFor(() => expect(onUndone).toHaveBeenCalled())
  expect(undo).toHaveBeenLastCalledWith(12, true)
})

test('an undone batch is struck through and has no Undo button', () => {
  renderWithProviders(<ChangeChips batch={{ ...batch, undone_at: '2026-10-07T15:00:00Z' }} onUndone={vi.fn()} />)
  expect(screen.getByText('Undone')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
})
