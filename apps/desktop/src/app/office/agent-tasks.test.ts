import { describe, expect, it } from 'vitest'

import { tasksForAgent, type OfficeKanbanBoard } from './agent-tasks'

const board: OfficeKanbanBoard = {
  columns: [
    {
      tasks: [
        { id: '1', title: 'A open', status: 'ready', assignee: 'alice' },
        { id: '2', title: 'B open', status: 'running', assignee: 'bob' },
        { id: '3', title: 'A done', status: 'archived', assignee: 'Alice' }
      ]
    }
  ]
}

describe('tasksForAgent', () => {
  it('returns active tasks for the assignee (case-insensitive)', () => {
    expect(tasksForAgent(board, 'alice', 'active').map(t => t.id)).toEqual(['1'])
  })

  it('returns archived tasks for the assignee', () => {
    expect(tasksForAgent(board, 'alice', 'archived').map(t => t.id)).toEqual(['3'])
  })

  it('returns empty for missing board or name', () => {
    expect(tasksForAgent(null, 'alice', 'active')).toEqual([])
    expect(tasksForAgent(board, '', 'active')).toEqual([])
  })
})
