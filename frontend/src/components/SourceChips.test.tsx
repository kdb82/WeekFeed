import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../test/render'
import type { Citation } from '../types'
import SourceChips from './SourceChips'

const citations: Citation[] = [
  { n: 1, source_type: 'item', source_id: 4, title: 'Token bug', meta: 'note · work › api-server · 2026-10-07',
    body: 'Token bug was clock skew', label: 'work', project_id: 1 },
  { n: 2, source_type: 'commit', source_id: 9, title: 'fix: refresh', meta: 'commit a1b2c3d · work › api-server · 2026-10-06',
    body: 'fix: refresh token\n\nFiles: auth/session.py', label: 'work', project_id: 1 },
]

test('chips expand and collapse their source', () => {
  renderWithProviders(<SourceChips citations={citations} />)
  expect(screen.queryByText(/Files: auth\/session.py/)).not.toBeInTheDocument()
  const chip = screen.getByRole('button', { name: /commit a1b2c3d/ })
  fireEvent.click(chip)
  expect(chip).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByText(/Files: auth\/session.py/)).toBeInTheDocument()
  fireEvent.click(chip)
  expect(screen.queryByText(/Files: auth\/session.py/)).not.toBeInTheDocument()
})

test('renders nothing without citations', () => {
  const { container } = renderWithProviders(<SourceChips citations={[]} />)
  expect(container.querySelector('button')).toBeNull()
})
