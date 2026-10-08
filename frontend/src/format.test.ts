import { relativeTime, scopeKey } from './format'

test('relativeTime buckets minutes, hours and days', () => {
  const now = new Date('2026-10-07T15:00:00Z')
  expect(relativeTime('2026-10-07T14:59:40Z', now)).toBe('just now')
  expect(relativeTime('2026-10-07T14:58:00Z', now)).toBe('2m ago')
  expect(relativeTime('2026-10-07T12:00:00Z', now)).toBe('3h ago')
  expect(relativeTime('2026-10-05T15:00:00Z', now)).toBe('2d ago')
})

test('scopeKey distinguishes project and label scopes', () => {
  expect(scopeKey({ label: 'work', projectId: 3 })).toBe('p3')
  expect(scopeKey({ label: 'work', projectId: null })).toBe('l:work')
})
