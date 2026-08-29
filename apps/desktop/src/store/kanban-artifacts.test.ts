import { afterEach, describe, expect, it } from 'vitest'

import {
  bindKanbanArtifactsForTurn,
  clearKanbanArtifacts,
  peekKanbanArtifacts,
  queueKanbanArtifacts,
  takeTurnBoundKanbanArtifacts
} from './kanban-artifacts'

describe('kanban-artifacts store', () => {
  afterEach(() => {
    clearKanbanArtifacts()
  })

  it('queues, binds on turn start, and drains on complete', () => {
    queueKanbanArtifacts('s1', ['/tmp/a.docx', '', '  ', '/tmp/a.docx', '/tmp/b.json'])

    expect(peekKanbanArtifacts('s1')).toEqual({
      pending: ['/tmp/a.docx', '/tmp/b.json'],
      turnBound: []
    })

    bindKanbanArtifactsForTurn('s1')

    expect(peekKanbanArtifacts('s1')).toEqual({
      pending: [],
      turnBound: ['/tmp/a.docx', '/tmp/b.json']
    })

    // A second completion while the turn is running stays pending.
    queueKanbanArtifacts('s1', ['/tmp/c.xlsx'])
    expect(peekKanbanArtifacts('s1').pending).toEqual(['/tmp/c.xlsx'])
    expect(peekKanbanArtifacts('s1').turnBound).toEqual(['/tmp/a.docx', '/tmp/b.json'])

    expect(takeTurnBoundKanbanArtifacts('s1')).toEqual(['/tmp/a.docx', '/tmp/b.json'])
    expect(peekKanbanArtifacts('s1')).toEqual({
      pending: ['/tmp/c.xlsx'],
      turnBound: []
    })

    bindKanbanArtifactsForTurn('s1')
    expect(takeTurnBoundKanbanArtifacts('s1')).toEqual(['/tmp/c.xlsx'])
    expect(peekKanbanArtifacts('s1')).toEqual({ pending: [], turnBound: [] })
  })

  it('scopes queues per session', () => {
    queueKanbanArtifacts('a', ['/tmp/a.docx'])
    queueKanbanArtifacts('b', ['/tmp/b.docx'])

    bindKanbanArtifactsForTurn('a')

    expect(takeTurnBoundKanbanArtifacts('a')).toEqual(['/tmp/a.docx'])
    expect(takeTurnBoundKanbanArtifacts('b')).toEqual([])
    expect(peekKanbanArtifacts('b').pending).toEqual(['/tmp/b.docx'])
  })
})
