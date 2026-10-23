import type { PreviewTarget } from '../../desktop/src/store/preview'
import { safeExternalUrl } from './adapter'
import { LocalFilePreview } from '@/app/chat/right-rail/preview-file'
import { ArtifactPreview } from '@/app/chat/right-rail/preview-artifact'
interface PreviewPaneProps {
  embedded?: boolean
  onClose?: () => void
  onRestartServer?: (url: string, context?: string) => Promise<string>
  reloadRequest?: number
  tabId?: string
  target: PreviewTarget
}
export function PreviewPane({ target, onClose, reloadRequest = 0 }: PreviewPaneProps) {
  // Only the Electron web guest needs replacing. File reads stay on the
  // renderer's profile-scoped remote FS API; artifacts keep their sandbox.
  if (target.kind === 'artifact') return <ArtifactPreview target={target} onClose={onClose} />
  if (target.kind === 'file') return <LocalFilePreview target={target} onClose={onClose} reloadKey={reloadRequest} />
  let url: string | null = null
  try { url = safeExternalUrl(target.url) } catch { /* Local/native targets have no browser equivalent. */ }
  return <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-sm text-muted-foreground" role="status">
    <p>The embedded browser requires Hermes Desktop.</p>
    {url && <a className="underline" href={url} target="_blank" rel="noopener noreferrer">Open this URL in a browser tab</a>}
  </div>
}
