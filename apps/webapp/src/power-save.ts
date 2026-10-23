export type KeepAwakeMode = 'off' | 'always' | 'while-working'
// Browser builds cannot acquire a native power-save blocker.
export const DEFAULT_KEEP_AWAKE_MODE: KeepAwakeMode = 'off'
export function parseKeepAwakeMode(value: unknown): KeepAwakeMode | null {
  if (value === true) return 'always'
  if (value === false) return 'off'
  return value === 'off' || value === 'always' || value === 'while-working' ? value : null
}
