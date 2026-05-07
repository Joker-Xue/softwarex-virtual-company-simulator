import test from 'node:test'
import assert from 'node:assert/strict'

import { deriveAgentWorldConnectionStatus } from './agentWorldConnectionStatus.js'

test('shows connected when world view is initialized with a profile even before websocket handshake completes', () => {
  const status = deriveAgentWorldConnectionStatus({
    hasProfile: true,
    initialized: true,
    wsConnected: false,
  })

  assert.equal(status.connected, true)
  assert.equal(status.label, '● Connected')
})

test('shows not connected before profile-driven initialization completes', () => {
  const status = deriveAgentWorldConnectionStatus({
    hasProfile: false,
    initialized: false,
    wsConnected: false,
  })

  assert.equal(status.connected, false)
  assert.equal(status.label, '○ Not connected')
})

test('stays connected after websocket handshake succeeds', () => {
  const status = deriveAgentWorldConnectionStatus({
    hasProfile: true,
    initialized: true,
    wsConnected: true,
  })

  assert.equal(status.connected, true)
  assert.equal(status.label, '● Connected')
})
