'use strict'

const path = require('node:path')

function getVenvPythonPath(venvRoot, platform = process.platform) {
  return path.join(venvRoot, platform === 'win32' ? path.join('Scripts', 'python.exe') : path.join('bin', 'python'))
}

function hasUsableActiveHermesInstall({ activeRoot, venvRoot, fileExists, directoryExists, platform = process.platform }) {
  if (!activeRoot || !venvRoot || typeof fileExists !== 'function' || typeof directoryExists !== 'function') {
    return false
  }

  return directoryExists(activeRoot) && fileExists(path.join(activeRoot, 'hermes_cli', 'main.py')) && fileExists(getVenvPythonPath(venvRoot, platform))
}

function hasValidBootstrapMarker(marker, schemaVersion) {
  return Boolean(
    marker &&
      typeof marker === 'object' &&
      marker.schemaVersion === schemaVersion &&
      typeof marker.pinnedCommit === 'string' &&
      marker.pinnedCommit.length >= 7
  )
}

function isBootstrapCompleteForInstall({
  marker,
  schemaVersion,
  activeRoot,
  venvRoot,
  fileExists,
  directoryExists,
  platform = process.platform
}) {
  if (!hasValidBootstrapMarker(marker, schemaVersion)) return false
  return hasUsableActiveHermesInstall({ activeRoot, venvRoot, fileExists, directoryExists, platform })
}

module.exports = {
  getVenvPythonPath,
  hasUsableActiveHermesInstall,
  hasValidBootstrapMarker,
  isBootstrapCompleteForInstall
}
