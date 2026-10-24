import type { HermesConnection } from '../../desktop/src/global'
export function resolveDesktopGatewayWsUrl(desktop: Window['hermesDesktop'], connection: HermesConnection): Promise<string> {
  return desktop.getGatewayWsUrl(connection.profile).then(result => {
    if (typeof result === 'string') return result
    if (result.ok) return result.wsUrl
    throw new Error(result.error)
  })
}
