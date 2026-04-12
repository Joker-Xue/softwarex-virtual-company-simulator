/**
 * Derive the viewer-facing connection badge for the virtual company page.
 *
 * We keep the actual WebSocket handshake state, but for the public demo we
 * consider the page "connected" once the world view has a profile and has
 * finished its initial data bootstrap. This avoids showing a misleading red
 * badge during startup or in constrained demo environments where the rest of
 * the world is already usable.
 */
export function deriveAgentWorldConnectionStatus({ hasProfile, initialized, wsConnected }) {
  const connected = Boolean(wsConnected || (hasProfile && initialized))

  return {
    connected,
    label: connected ? '● Connected' : '○ Not connected',
  }
}
