import { atom } from 'nanostores'
export const $diskPluginsScanPending = atom(false)
export const discoverRuntimePlugins = async (): Promise<void> => {}
export function watchRuntimePlugins(): void {}
export async function uninstallDiskPlugin(): Promise<{ ok: boolean; error: string }> {
  return { ok: false, error: 'Runtime Desktop plugins are unavailable in the browser.' }
}
