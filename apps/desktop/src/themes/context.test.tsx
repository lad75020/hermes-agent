import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { __resetBackendSkinSync, ingestBackendSkin } from './backend-sync'
import { contrastRatio, mix } from './color'
import { skinPref, ThemeProvider, useTheme } from './context'
import { everforestTheme, githubContrastTheme } from './presets'

// The live-authoring loop: Hermes writes/edits one skin file and every surface
// repaints. An in-place edit keeps the NAME — only the palette moves.
const bloomberg = (foreground: string) => ({
  name: 'bloomberg',
  colors: { background: '#000000', ui_text: foreground, ui_accent: '#ff8000' }
})

const cssVar = (name: string) => window.document.documentElement.style.getPropertyValue(name)

describe('ThemeProvider ← backend skin sync', () => {
  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(cleanup)

  it('applies an activated backend skin', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))

    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')
    expect(cssVar('--theme-background-seed')).toBe('#000000')
  })

  it('repaints an in-place edit of the ACTIVE skin (same name, new palette)', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))
    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')

    // Recolor the same skin file. The same-name apply guard correctly no-ops
    // (protects manual desktop picks), so the repaint must come from the
    // registry update reaching the active theme derivation.
    act(() => ingestBackendSkin(bloomberg('#ff2d95'), { apply: true }))
    expect(cssVar('--theme-foreground')).toBe('#ff2d95')
  })

  it('does not repaint an edit to an INACTIVE skin', () => {
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: true }))

    // A different skin registered without apply (e.g. seeded on reconnect)
    // must not touch the painted theme.
    act(() =>
      ingestBackendSkin({ name: 'forest', colors: { background: '#001100', ui_text: '#66ff66' } }, { apply: false })
    )
    expect(cssVar('--theme-foreground')).toBe('#ff9f0a')
  })

  // The relaunch bug: the persisted pick was a backend skin, and the boot paint
  // ran before the gateway seeded it. `normalizeSkin` could not resolve the
  // name, flattened it to the default, and the connect-time seed (apply: false,
  // by design) never repainted — so the theme "didn't stick" until `/skin`.
  it('paints a persisted backend skin once the connect-time seed makes it resolvable', () => {
    window.localStorage.setItem('hermes-desktop-theme-v2', 'bloomberg')

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    // Boot: nothing resolves 'bloomberg' yet → default paint...
    expect(cssVar('--theme-background-seed')).not.toBe('#000000')

    // ...but the pick survives, so the seed alone repaints it.
    act(() => ingestBackendSkin(bloomberg('#ff9f0a'), { apply: false }))

    expect(cssVar('--theme-background-seed')).toBe('#000000')
    expect(skinPref.resolve('default')).toBe('bloomberg')
  })
})

describe('ThemeProvider highlight preview', () => {
  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(cleanup)

  // Read the live context so the tests drive the real provider, not a mock.
  let ctx: ReturnType<typeof useTheme>

  function Probe() {
    ctx = useTheme()

    return null
  }

  const renderProbe = () =>
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    )

  it('paints the previewed theme without persisting it', () => {
    renderProbe()

    const committed = ctx.themeName

    act(() => ctx.previewTheme('everforest', 'dark'))

    expect(cssVar('--theme-foreground')).toBe(everforestTheme.darkColors!.foreground)
    // The commit surface does not change. The context name and the stored
    // preference keep their values.
    expect(ctx.themeName).toBe(committed)
    expect(skinPref.resolve('default')).toBe(committed)
  })

  it('clearThemePreview repaints the committed appearance', () => {
    renderProbe()

    act(() => ctx.previewTheme('everforest', 'dark'))
    expect(cssVar('--theme-foreground')).toBe(everforestTheme.darkColors!.foreground)

    act(() => ctx.clearThemePreview())
    expect(cssVar('--theme-foreground')).not.toBe(everforestTheme.darkColors!.foreground)
  })

  it('a commit replaces the preview and persists', () => {
    renderProbe()

    act(() => ctx.previewTheme('everforest', 'dark'))
    act(() => ctx.setTheme('mono'))

    expect(ctx.themeName).toBe('mono')
    expect(skinPref.resolve('default')).toBe('mono')
    expect(cssVar('--theme-foreground')).not.toBe(everforestTheme.darkColors!.foreground)
  })

  it('ignores a preview of an unknown theme', () => {
    renderProbe()

    const painted = cssVar('--theme-foreground')

    act(() => ctx.previewTheme('does-not-exist', 'dark'))
    expect(cssVar('--theme-foreground')).toBe(painted)
  })
})

describe('GitHub Contrast readability settings', () => {
  beforeEach(() => {
    window.localStorage.clear()
    __resetBackendSkinSync()
  })

  afterEach(cleanup)

  it('restores default readability values when switching back to GitHub', () => {
    let current!: ReturnType<typeof useTheme>

    function Probe() {
      current = useTheme()

      return null
    }

    window.localStorage.setItem('hermes-desktop-theme-v2', 'github-contrast')
    window.localStorage.setItem('hermes-desktop-mode-v1', 'light')

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    )

    expect(cssVar('--conversation-scaffold-opacity')).toBe('0.9')

    act(() => current.setTheme('github'))

    expect(window.document.documentElement.dataset.hermesTheme).toBe('github')
    expect(cssVar('--theme-text-primary-strength')).toBe('94%')
    expect(cssVar('--theme-text-secondary-strength')).toBe('74%')
    expect(cssVar('--theme-text-tertiary-strength')).toBe('54%')
    expect(cssVar('--theme-text-quaternary-strength')).toBe('36%')
    expect(cssVar('--theme-scaffold-text-strength')).toBe('64%')
    expect(cssVar('--theme-scaffold-meta-strength')).toBe('44%')
    expect(cssVar('--conversation-scaffold-opacity')).toBe('0.67')
  })

  it.each(['light', 'dark'] as const)('applies AA transcript scaffolding in %s mode', mode => {
    window.localStorage.setItem('hermes-desktop-theme-v2', 'github-contrast')
    window.localStorage.setItem('hermes-desktop-mode-v1', mode)

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>
    )

    const palette = mode === 'dark' ? githubContrastTheme.darkColors! : githubContrastTheme.colors
    const scaffoldOpacity = Number(cssVar('--conversation-scaffold-opacity'))
    const strength = (name: string) => Number.parseFloat(cssVar(name)) / 100

    const chatSurface = mix(palette.background, mode === 'dark' ? '#0d0d0e' : '#f3f3f3', mode === 'dark' ? 0.26 : 0.08)

    const effectiveScaffold = (name: string) => mix(chatSurface, palette.foreground, strength(name) * scaffoldOpacity)

    expect(window.document.documentElement.dataset.hermesTheme).toBe('github-contrast')
    expect(window.document.documentElement.dataset.hermesMode).toBe(mode)
    expect(cssVar('--theme-background-seed')).toBe(palette.background)
    expect(cssVar('--theme-text-primary-strength')).toBe('100%')
    expect(cssVar('--theme-text-secondary-strength')).toBe('90%')
    expect(cssVar('--theme-text-tertiary-strength')).toBe('78%')
    expect(cssVar('--theme-text-quaternary-strength')).toBe('66%')
    expect(cssVar('--theme-scaffold-text-strength')).toBe('90%')
    expect(cssVar('--theme-scaffold-meta-strength')).toBe('78%')
    expect(scaffoldOpacity).toBe(0.9)
    expect(contrastRatio(effectiveScaffold('--theme-scaffold-text-strength'), chatSurface)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(effectiveScaffold('--theme-scaffold-meta-strength'), chatSurface)).toBeGreaterThanOrEqual(4.5)
  })
})
