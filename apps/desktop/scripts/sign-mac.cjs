const { sign } = require('@electron/osx-sign')

/**
 * electron-builder 26.8.x resolves the selected macOS signing identity with a
 * SHA-1 hash, but its default signing path passes the certificate common name
 * back to @electron/osx-sign. If the login keychain contains duplicate valid
 * Developer ID certificates with the same common name, macOS codesign rejects
 * the name as ambiguous.
 *
 * electron-builder already passes the unambiguous SHA-1 in configuration.identity
 * to custom sign hooks, so delegate to @electron/osx-sign directly with that
 * configuration instead of falling back to the default name-based path.
 */
module.exports = async function signMac(configuration) {
  if (configuration.identity) {
    console.log(`[sign-mac] signing with identity ${configuration.identity}`)
  }

  await sign(configuration)
}
