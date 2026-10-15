export type KeepAwakeMode = 'off' | 'always' | 'while-working'
export function parseKeepAwakeMode(value: unknown): KeepAwakeMode | null {
  if (value === true) return 'always'
  if (value === false) return 'off'
  return value === 'off' || value === 'always' || value === 'while-working' ? value : null
}
