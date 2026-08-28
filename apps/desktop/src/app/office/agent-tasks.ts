/** Minimal kanban task shape used by the office agent modal. */
export interface OfficeKanbanTask {
  id: string
  title?: string | null
  status: string
  assignee?: null | string
}

export interface OfficeKanbanBoard {
  columns: Array<{ tasks: OfficeKanbanTask[] }>
}

/** Flatten board columns and keep tasks assigned to `agentName`. */
export function tasksForAgent(
  board: OfficeKanbanBoard | null | undefined,
  agentName: string,
  mode: 'active' | 'archived'
): OfficeKanbanTask[] {
  if (!board || !agentName) return []
  const needle = agentName.trim().toLowerCase()
  if (!needle) return []

  return board.columns
    .flatMap(column => column.tasks)
    .filter(task => {
      const assignee = (task.assignee ?? '').trim().toLowerCase()
      if (assignee !== needle) return false
      const archived = task.status === 'archived'
      return mode === 'archived' ? archived : !archived
    })
}
