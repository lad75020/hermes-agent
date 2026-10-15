import { vi } from 'vitest'
// Use browser Storage semantics, independent of Node's experimental global.
for (const name of ['localStorage', 'sessionStorage']) {
  const values = new Map<string, string>()
  const storage: Storage = {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: key => values.get(String(key)) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => { values.delete(String(key)) },
    setItem: (key, value) => { values.set(String(key), String(value)) }
  }
  Object.defineProperty(window, name, { value: storage, configurable: true })
  vi.stubGlobal(name, storage)
}
Object.defineProperty(window, 'matchMedia', { value: vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })) })
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} })
vi.stubGlobal('CSS', { escape: (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, char => `\\${char}`), supports: () => false })
Element.prototype.scrollIntoView = () => {}
Element.prototype.scrollTo = () => {}
