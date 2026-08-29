/**
 * Session-scoped queue for Kanban completion artifacts delivered via
 * `status.update { kind: 'kanban', artifacts: [...] }`.
 *
 * Lifecycle:
 * 1. status.update → `queueKanbanArtifacts` (pending)
 * 2. message.start → `bindKanbanArtifactsForTurn` (pending → turnBound)
 * 3. message.complete → `takeTurnBoundKanbanArtifacts` stamped onto the
 *    settled assistant bubble as `ChatMessage.kanbanArtifacts`
 *
 * Binding on message.start keeps a mid-turn second completion from landing
 * on the wrong wake reply: its artifacts stay in `pending` until the next
 * start.
 */

export interface SessionKanbanArtifacts {
  pending: string[]
  turnBound: string[]
}

const EMPTY: SessionKanbanArtifacts = { pending: [], turnBound: [] }

const bySession = new Map<string, SessionKanbanArtifacts>()

function normalizePaths(paths: readonly unknown[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()

  for (const raw of paths) {
    if (typeof raw !== 'string') {
      continue
    }

    const path = raw.trim()

    if (!path || seen.has(path)) {
      continue
    }

    seen.add(path)
    out.push(path)
  }

  return out
}

function read(sessionId: string): SessionKanbanArtifacts {
  return bySession.get(sessionId) ?? EMPTY
}

function write(sessionId: string, next: SessionKanbanArtifacts) {
  if (next.pending.length === 0 && next.turnBound.length === 0) {
    bySession.delete(sessionId)

    return
  }

  bySession.set(sessionId, next)
}

export function queueKanbanArtifacts(sessionId: string, paths: readonly unknown[]) {
  if (!sessionId) {
    return
  }

  const incoming = normalizePaths(paths)

  if (incoming.length === 0) {
    return
  }

  const cur = read(sessionId)
  const pending = normalizePaths([...cur.pending, ...incoming])

  write(sessionId, { pending, turnBound: cur.turnBound })
}

/** Move pending paths onto the turn that is about to start. */
export function bindKanbanArtifactsForTurn(sessionId: string) {
  if (!sessionId) {
    return
  }

  const cur = read(sessionId)

  if (cur.pending.length === 0) {
    return
  }

  write(sessionId, {
    pending: [],
    turnBound: normalizePaths([...cur.turnBound, ...cur.pending])
  })
}

/** Drain turn-bound paths for stamping onto the settled assistant message. */
export function takeTurnBoundKanbanArtifacts(sessionId: string): string[] {
  if (!sessionId) {
    return []
  }

  const cur = read(sessionId)
  const taken = cur.turnBound

  write(sessionId, { pending: cur.pending, turnBound: [] })

  return taken
}

/** Test / debug helper. */
export function peekKanbanArtifacts(sessionId: string): SessionKanbanArtifacts {
  const cur = read(sessionId)

  return { pending: [...cur.pending], turnBound: [...cur.turnBound] }
}

/** Test helper. */
export function clearKanbanArtifacts(sessionId?: string) {
  if (sessionId) {
    bySession.delete(sessionId)

    return
  }

  bySession.clear()
}
