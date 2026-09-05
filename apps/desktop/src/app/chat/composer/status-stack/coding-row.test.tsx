import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { atom } from 'nanostores'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { type SessionView, SessionViewProvider } from '@/app/chat/session-view'
import { $notifications, clearNotifications } from '@/store/notifications'
import { $currentUsage } from '@/store/session'

vi.mock('@/store/coding-status', () => ({
  registerRepoStatusCwd: () => undefined,
  repoStatusForCwd: (cwd?: string) =>
    atom(
      cwd === '/not-a-repo'
        ? null
        : {
      added: 12,
      ahead: 0,
      behind: 0,
      branch: 'bb/hitbox',
      defaultBranch: 'main',
      detached: false,
      removed: 3,
      untracked: 0
          }
    ),
  repoWorktreesForCwd: () => atom([])
}))

const { CodingStatusRow } = await import('./coding-row')

describe('CodingStatusRow', () => {
  afterEach(() => {
    cleanup()
    $currentUsage.set({ calls: 0, input: 0, output: 0, total: 0 })
  })

  it('shows this session total token input and output immediately before the line count', () => {
    $currentUsage.set({ calls: 2, input: 1_230, output: 456, total: 1_686 })

    render(<CodingStatusRow onOpen={() => undefined} repoPath="/repo" />)

    const usage = screen.getByText('1.2k in · 456 out')
    const lineCount = screen.getByText('12').closest('button')

    expect(usage.getAttribute('data-slot')).toBe('session-token-usage')
    expect(lineCount).not.toBeNull()
    expect(usage.compareDocumentPosition(lineCount!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('reads token totals from the tile session rather than the primary session', () => {
    $currentUsage.set({ calls: 1, input: 999, output: 999, total: 1_998 })

    const tileView = {
      ...({} as SessionView),
      $usage: atom({ calls: 3, input: 12_000, output: 3_400, total: 15_400 }),
      kind: 'tile'
    } satisfies SessionView

    render(
      <SessionViewProvider value={tileView}>
        <CodingStatusRow onOpen={() => undefined} repoPath="/repo" />
      </SessionViewProvider>
    )

    expect(screen.getByText('12k in · 3.4k out')).toBeTruthy()
    expect(screen.queryByText('999 in · 999 out')).toBeNull()
  })

  it('keeps token totals visible when the session is outside a git repository', () => {
    $currentUsage.set({ calls: 1, input: 81, output: 19, total: 100 })

    render(<CodingStatusRow onOpen={() => undefined} repoPath="/not-a-repo" />)

    expect(screen.getByText('81 in · 19 out')).toBeTruthy()
    expect(screen.queryByText('bb/hitbox')).toBeNull()
  })

  it('opens the review pane from the branch and the diff counts, never the bar itself', () => {
    const onOpen = vi.fn()

    const { container } = render(<CodingStatusRow onOpen={onOpen} repoPath="/repo" />)

    const bar = container.querySelector<HTMLElement>('.coding-status-bar')

    expect(bar).not.toBeNull()

    fireEvent.click(bar!)
    expect(onOpen).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('bb/hitbox'))
    expect(onOpen).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText('12'))
    expect(onOpen).toHaveBeenCalledTimes(2)
  })

  it('wraps the click targets without adding a layout box', () => {
    const { container } = render(<CodingStatusRow onOpen={() => undefined} repoPath="/repo" />)

    // `display: contents` is what keeps the branch label and the counts direct
    // flex children of the row — the hit areas cost nothing visually.
    expect(screen.getByText('bb/hitbox').parentElement?.classList.contains('contents')).toBe(true)
    expect(screen.getByText('12').closest('button')?.classList.contains('contents')).toBe(true)
    // The glyph button fills the row's existing 3.5 leading slot exactly.
    expect(container.querySelector('button[class~="size-3.5"]')).not.toBeNull()
  })

  it('parks the copy glyph against the end of the path, not the end of the row', () => {
    render(<CodingStatusRow onOpen={() => undefined} repoPath="/Users/someone/www/repo" />)

    const path = screen.getByText('~/www/repo')

    // The path sizes to its content and the glyph is its immediate sibling, so
    // the pair reads as one unit. `flex-1` belongs to the wrapper (which holds
    // the row's slack open) — on the label it stretched the text and pushed the
    // glyph out to the kebab.
    expect(path.classList.contains('flex-1')).toBe(false)
    expect(path.parentElement?.classList.contains('flex-1')).toBe(true)
    expect(path.nextElementSibling?.tagName).toBe('BUTTON')
  })

  it('copies the absolute cwd inline — checkmark feedback, no toast', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    clearNotifications()

    render(<CodingStatusRow onOpen={() => undefined} repoPath="/Users/someone/www/repo" />)

    // Painted tildified, copied raw.
    expect(screen.getByText('~/www/repo')).toBeTruthy()

    const copy = screen.getByRole('button', { name: 'Copy path' })

    fireEvent.click(copy)

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('/Users/someone/www/repo'))
    // Confirmation is the button turning into a checkmark, not a notification.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Copied' })).toBeTruthy())
    expect($notifications.get()).toHaveLength(0)
  })
})
