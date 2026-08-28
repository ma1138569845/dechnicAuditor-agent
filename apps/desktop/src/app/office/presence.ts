/**
 * Work-centric office presence.
 *
 * Primary badge is only idle | busy (whether the agent has open work).
 * Messaging-gateway up/down is a secondary signal — not “offline at the desk”.
 */
export type OfficePresence = 'idle' | 'busy'

export function resolveOfficePresence(busy: boolean): OfficePresence {
  return busy ? 'busy' : 'idle'
}
