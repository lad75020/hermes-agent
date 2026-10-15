import { atom } from 'nanostores'
import type { KeepAwakeMode } from './power-save'
export type { KeepAwakeMode }
export const $keepAwakeMode = atom<KeepAwakeMode>('off')
export function setKeepAwakeMode(mode: KeepAwakeMode): void {
  if (mode !== 'off') window.dispatchEvent(new CustomEvent('hermes-capability-error', { detail: 'Keeping the computer awake requires Hermes Desktop. Browser power controls are unavailable.' }))
  $keepAwakeMode.set('off')
}
