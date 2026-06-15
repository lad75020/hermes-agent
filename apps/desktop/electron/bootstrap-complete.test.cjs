const assert = require('node:assert/strict')
const test = require('node:test')
const path = require('node:path')

const {
  getVenvPythonPath,
  hasUsableActiveHermesInstall,
  hasValidBootstrapMarker,
  isBootstrapCompleteForInstall
} = require('./bootstrap-complete.cjs')

function makeProbe(existingFiles = [], existingDirs = []) {
  const files = new Set(existingFiles)
  const dirs = new Set(existingDirs)
  return {
    fileExists: filePath => files.has(filePath),
    directoryExists: dirPath => dirs.has(dirPath)
  }
}

test('hasUsableActiveHermesInstall accepts an existing checkout and venv without a desktop marker', () => {
  const root = '/Volumes/WDBlack4TB/.hermes/hermes-agent'
  const venv = path.join(root, 'venv')
  const python = getVenvPythonPath(venv, 'darwin')
  const probes = makeProbe([path.join(root, 'hermes_cli', 'main.py'), python], [root])

  assert.equal(
    hasUsableActiveHermesInstall({
      activeRoot: root,
      venvRoot: venv,
      platform: 'darwin',
      ...probes
    }),
    true
  )
})

test('hasUsableActiveHermesInstall rejects partial installs without a venv python', () => {
  const root = '/tmp/hermes-agent'
  const probes = makeProbe([path.join(root, 'hermes_cli', 'main.py')], [root])

  assert.equal(
    hasUsableActiveHermesInstall({
      activeRoot: root,
      venvRoot: path.join(root, 'venv'),
      platform: 'darwin',
      ...probes
    }),
    false
  )
})

test('isBootstrapCompleteForInstall still requires a valid marker schema when checking marker completion', () => {
  const root = '/tmp/hermes-agent'
  const venv = path.join(root, 'venv')
  const probes = makeProbe([path.join(root, 'hermes_cli', 'main.py'), getVenvPythonPath(venv, 'darwin')], [root])

  assert.equal(hasValidBootstrapMarker({ schemaVersion: 1, pinnedCommit: 'abcdef0' }, 1), true)
  assert.equal(
    isBootstrapCompleteForInstall({
      marker: { schemaVersion: 1, pinnedCommit: 'abcdef0' },
      schemaVersion: 1,
      activeRoot: root,
      venvRoot: venv,
      platform: 'darwin',
      ...probes
    }),
    true
  )
  assert.equal(
    isBootstrapCompleteForInstall({
      marker: null,
      schemaVersion: 1,
      activeRoot: root,
      venvRoot: venv,
      platform: 'darwin',
      ...probes
    }),
    false
  )
})
