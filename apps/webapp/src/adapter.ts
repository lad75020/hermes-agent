import type { DesktopConnectionsRegistry, HermesConnection, DesktopProfileRoute } from '../../desktop/src/global'
import { browserApi, gatewayWsUrl } from './transport'
import { getApiRequestProfile } from '@/api/client'

const subscribe = () => () => {}
export function unsupported(feature: string): never {
  const message = `${feature} requires the native Desktop app and is unavailable in this browser.`
  window.dispatchEvent(new CustomEvent('hermes-capability-error', { detail: message }))
  throw new Error(message)
}
export function safeExternalUrl(raw: string): string {
  const url = new URL(raw)
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Only HTTP(S) links without credentials can be opened')
  return url.href
}
const profileKey = 'hermes.webapp.profile.v1'
const defaultKey = 'hermes.webapp.defaultProfile.v1'
export function createBrowserAdapter() {
  const registry: DesktopConnectionsRegistry = {
    version: 2, primary: 'browser', secureTokenStorage: false,
    connections: [{ id: 'browser', label: location.host, kind: 'remote', url: location.origin, authMode: 'oauth', tokenSet: false, tokenPreview: null }]
  }
  const selectedProfile = (profile?: string | null) => profile === undefined ? localStorage.getItem(profileKey) || 'default' : profile || 'default'
  const snapshot = () => structuredClone(registry)
  const descriptor = async (profile?: string | null): Promise<HermesConnection> => ({
    baseUrl: location.origin, wsUrl: `${location.origin.replace(/^http/, 'ws')}/api/ws`, token: '',
    mode: 'remote', authMode: 'oauth', remoteKind: 'url', source: 'settings',
    isFullscreen: false, nativeOverlayWidth: 0, windowButtonPosition: null,
    logs: [], profile: selectedProfile(profile),
    connectionId: 'browser', registryScoped: true, sharedRemote: true
  })
  const checkConnection = (id?: string | null) => {
    if (id && id !== 'browser') throw new Error('Backend selection belongs to the web service operator')
  }
  const getDefault = async (): Promise<DesktopProfileRoute | null> => {
    const profile = localStorage.getItem(defaultKey)
    return profile ? { connectionId: 'browser', profile } : null
  }
  const remember = async (name: string | null) => {
    if (name) localStorage.setItem(profileKey, name); else localStorage.removeItem(profileKey)
    return { profile: name, inherited: false }
  }
  const openExternal = async (url: string) => { window.open(safeExternalUrl(url), '_blank', 'noopener,noreferrer') }
  const bridge = {
    api: browserApi,
    getConnection: descriptor,
    getConnectionFor: async (route: { connectionId?: string | null; profile?: string | null }) => { checkConnection(route.connectionId); return descriptor(route.profile) },
    getGatewayWsUrl: (profile?: string | null) => gatewayWsUrl(selectedProfile(profile)),
    getGatewayWsUrlFor: async (route: { connectionId?: string | null; profile?: string | null }) => { checkConnection(route.connectionId); return gatewayWsUrl(selectedProfile(route.profile)) },
    getProfileRoutes: async (profiles: string[]) => profiles.map(profile => ({ connectionId: 'browser', mode: 'remote', primary: true, profile, targetProfile: profile })),
    revalidateConnection: async () => { await browserApi({ path: '/api/auth/me' }); return { ok: true, rebuilt: false } },
    getBootProgress: async () => ({ error: null, fakeMode: false, running: false, progress: 100, phase: 'browser.ready', message: 'Browser connected', timestamp: Date.now() }),
    getBootstrapState: async () => ({ active: false, stages: {}, log: [], error: null, manifest: null, startedAt: null, completedAt: null, setupChoice: null, unsupportedPlatform: null, bundled: false }),
    getConnectionConfig: async () => ({ mode: 'remote', remoteUrl: location.origin, remoteAuthMode: 'oauth', remoteTokenSet: false, remoteTokenPreview: null, envOverride: true, profile: null, remoteOauthConnected: true, secureTokenStorage: false, remoteTokenPlainText: false, cloudOrg: '', sshHost: '', sshUser: '', sshPort: null, sshKeyPath: '', sshRemoteHermesPath: '', sshRemoteProfile: '' }),
    connections: { list: async () => snapshot(), setLastUsed: async (id: string) => { checkConnection(id); return { ok: true, registry: snapshot() } }, onChanged: subscribe,
      save: async () => unsupported('Gateway configuration'), remove: async () => unsupported('Gateway configuration'), setPrimary: async () => unsupported('Gateway configuration'), test: async (id: string) => { checkConnection(id); await browserApi({ path: '/api/auth/me' }); return { ok: true } } },
    profile: { get: async () => ({ profile: localStorage.getItem(profileKey), inherited: false }), remember, set: remember, getDefault,
      setDefault: async (route: DesktopProfileRoute) => { checkConnection(route.connectionId); localStorage.setItem(defaultKey, route.profile); return route }, onDefaultChanged: subscribe },
    openExternal, openPreviewInBrowser: openExternal,
    writeClipboard: async (text: string) => { await navigator.clipboard.writeText(text); return true },
    readClipboard: async () => navigator.clipboard.readText(),
    windowControls: { custom: false, minimize: () => unsupported('Window controls'), toggleMaximize: () => unsupported('Window controls'), close: () => unsupported('Window controls') },
    glassSupported: false, translucencySupported: false,
    setActiveWork: () => {}, setTitleBarTheme: () => {}, setNativeTheme: () => {},
    getOnBattery: async () => false,
    claimAmbientCue: async () => true,
    notify: async () => false,
    requestMicrophoneAccess: async () => { window.dispatchEvent(new CustomEvent('hermes-capability-error', { detail: 'Microphone capture is unavailable in this browser build. Use Hermes Desktop for voice input.' })); return false },
    settings: {
      getDefaultProjectDir: async () => { const data = await browserApi<{ cwd: string }>({ path: '/api/fs/default-cwd', profile: getApiRequestProfile() }); return { defaultLabel: 'Backend workspace', dir: null, resolvedCwd: data.cwd } },
      pickDefaultProjectDir: async () => unsupported('Native folder picker'), setDefaultProjectDir: async () => unsupported('Native folder preference')
    },
    logLine: () => {}, reportRendererError: (error: unknown) => console.error('Hermes renderer:', error),
    getRecentLogs: async () => ({ path: '', lines: ['Browser diagnostics are available in the browser developer console.'] }),
    getSyncStatus: async () => null, getRemoteDisplayReason: async () => null,
    getVersion: async () => ({ appVersion: 'webapp', electronVersion: '', nodeVersion: '', hermesRoot: '', platform: 'browser', updateMechanism: 'external' }),
    getSecretStorageEncryption: async () => ({ on: false }),
    getPathForFile: () => '',
    readFileDataUrl: async () => unsupported('Native filesystem reads'),
    readFileDataUrlForAttach: async () => unsupported('Native attachment filesystem reads'),
    readFileText: async () => unsupported('Native filesystem reads'),
    saveImageBuffer: async () => unsupported('Native attachment staging'),
    saveClipboardImage: async () => unsupported('Native clipboard image staging'),
    savePastedText: async () => unsupported('Native pasted-text staging'),
    saveTextFileAs: async () => unsupported('Native text export dialog'),
    selectPaths: async () => unsupported('Native file picker'),
    openDir: async () => unsupported('Native folder picker'),
    openSessionInTerminal: async () => unsupported('External terminal'),
    openSessionWindow: async () => unsupported('Native session window'),
    openWindow: async () => unsupported('Native app window'),
    openBrowserWindow: async () => unsupported('Embedded Electron browser'),
    revealPath: async () => false,
    revealLogs: async () => unsupported('Native log viewer'),
    saveConnectionConfig: async () => unsupported('Gateway configuration'),
    applyConnectionConfig: async () => unsupported('Gateway configuration'),
    testConnectionConfig: async () => unsupported('Gateway configuration'),
    probeConnectionConfig: async () => unsupported('Gateway configuration'),
    sshConfigHosts: async () => unsupported('SSH configuration'),
    sshResolveHost: async () => unsupported('SSH configuration'),
    setSecretStorageEncryption: async () => unsupported('Native credential storage'),
    oauthLoginConnectionConfig: async () => { location.assign('/login?next=%2F'); return { ok: false, connected: false, baseUrl: location.origin } },
    oauthLogoutConnectionConfig: async () => unsupported('Use the browser Sign out button'),
    findInPage: async () => unsupported('Use the browser Find menu'),
    stopFindInPage: async () => {},
    themes: { fetchMarketplace: async () => unsupported('Native theme marketplace'), searchMarketplace: async () => unsupported('Native theme marketplace') },
    quickEntry: { getSettings: async () => ({ enabled: false, registered: false, shortcut: '', error: null }), setSettings: async () => unsupported('Global shortcuts'), onSubmit: subscribe, onLateResult: subscribe, onState: subscribe, onShown: subscribe, pushState: () => {}, ackSubmit: () => {}, dismiss: () => {}, submit: async () => unsupported('Global shortcuts') },
    petOverlay: { onControl: subscribe, onState: subscribe, pushState: () => {}, setBounds: () => {}, setIgnoreMouse: () => {}, setFocusable: () => {}, control: () => {}, open: async () => unsupported('Pet overlay'), close: async () => ({ ok: true }) },
    updates: { check: async () => ({ available: false, supported: false, currentVersion: 'webapp' }), apply: async () => unsupported('Native updater'), onProgress: subscribe },
    onBootProgress: subscribe, onBackendExit: subscribe, onBootstrapEvent: subscribe,
    onBrowserPopoutClosed: subscribe, onPreviewFileChanged: subscribe,
    onFoundInPage: subscribe, onOpenFindBarRequested: subscribe,
    onBatteryChanged: subscribe, onPowerResume: subscribe,
    onWindowStateChanged: subscribe, onConnectionApplied: subscribe,
    onExternalOpenFailed: subscribe, onClosePreviewRequested: subscribe, onPreviewNav: subscribe,
    onOpenFolderRequested: subscribe, onOpenUpdatesRequested: subscribe, onDeepLink: subscribe,
    onFocusSession: subscribe, onNotificationAction: subscribe, onNotificationActivate: subscribe
  } satisfies Partial<Window['hermesDesktop']>
  // The shared renderer declares the full native preload contract. This browser implements
  // its supported subset; absent optional capabilities remain absent (no catch-all IPC shim).
  return bridge as unknown as Window['hermesDesktop']
}
