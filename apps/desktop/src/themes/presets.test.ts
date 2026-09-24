import { describe, expect, it } from 'vitest'

import { contrastRatio } from '@hermes/shared/color'
import {
  BUILTIN_THEME_LIST,
  BUILTIN_THEMES,
  DEFAULT_SKIN_NAME,
  DEFAULT_TYPOGRAPHY,
  EMOJI_FALLBACK,
  githubContrastTheme,
  githubTheme,
  nousAltTheme
} from './presets'

// #40364: none of the UI text/mono fonts carry emoji glyphs, so every font
// stack must end with a color-emoji fallback or emoji render as tofu on
// platforms whose default font lacks them (e.g. Linux).
describe('theme typography emoji fallback (#40364)', () => {
  const stacks: Array<[string, string]> = [
    ['DEFAULT_TYPOGRAPHY.fontSans', DEFAULT_TYPOGRAPHY.fontSans],
    ['DEFAULT_TYPOGRAPHY.fontMono', DEFAULT_TYPOGRAPHY.fontMono],
    // A theme may override only fontMono (fontSans then falls back to the
    // default, which already carries the emoji stack), so skip undefined.
    ...BUILTIN_THEME_LIST.flatMap(theme =>
      (
        [
          [`${theme.name}.fontSans`, theme.typography?.fontSans],
          [`${theme.name}.fontMono`, theme.typography?.fontMono]
        ] as Array<[string, string | undefined]>
      ).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    )
  ]

  it.each(stacks)('%s includes a color-emoji font', (_label, stack) => {
    expect(stack).toMatch(/Apple Color Emoji|Segoe UI Emoji|Noto Color Emoji|(^|,\s*)emoji\b/)
  })
})

describe('GitHub Contrast', () => {
  const backgroundKeys = ['background', 'card', 'muted', 'popover', 'input', 'sidebarBackground', 'userBubble'] as const

  it('is registered as a separate built-in without replacing GitHub', () => {
    expect(githubContrastTheme.name).toBe('github-contrast')
    expect(githubContrastTheme.label).toBe('GitHub Contrast')
    expect(BUILTIN_THEMES['github-contrast']).toBe(githubContrastTheme)
    expect(BUILTIN_THEMES.github).toBe(githubTheme)
    expect(githubContrastTheme).not.toBe(githubTheme)
  })

  it('inherits GitHub surfaces, typography, and terminal palettes in both modes', () => {
    for (const key of backgroundKeys) {
      expect(githubContrastTheme.colors[key]).toBe(githubTheme.colors[key])
      expect(githubContrastTheme.darkColors?.[key]).toBe(githubTheme.darkColors?.[key])
    }

    expect(githubContrastTheme.typography).toBe(githubTheme.typography)
    expect(githubContrastTheme.terminal).toBe(githubTheme.terminal)
    expect(githubContrastTheme.darkTerminal).toBe(githubTheme.darkTerminal)
  })

  it('materially strengthens foregrounds and borders in both modes', () => {
    for (const [base, contrast] of [
      [githubTheme.colors, githubContrastTheme.colors],
      [githubTheme.darkColors!, githubContrastTheme.darkColors!]
    ]) {
      expect(contrastRatio(contrast.foreground, contrast.background)).toBeGreaterThan(
        contrastRatio(base.foreground, base.background)! + 1
      )
      expect(contrastRatio(contrast.mutedForeground, contrast.muted)).toBeGreaterThan(
        contrastRatio(base.mutedForeground, base.muted)! + 2
      )
      expect(contrastRatio(contrast.border, contrast.background)).toBeGreaterThanOrEqual(3)
      expect(contrastRatio(contrast.border, contrast.background)).toBeGreaterThan(
        contrastRatio(base.border, base.background)! * 1.5
      )
    }
  })
})
