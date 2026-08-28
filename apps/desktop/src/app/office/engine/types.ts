// Ported from hermes-studio-vue `packages/client/src/api/hermes/office.ts`
// (OfficeAction union). Desktop has no /api/hermes/office backend — actions
// are dispatched in-process from the office store to the Pixi scene, so the
// type is defined locally.

export interface DeskVisitAction {
  type: 'desk_visit'
  visitor: string
  host: string
  message?: string
}

export interface DeskVisitTourAction {
  type: 'desk_visit_tour'
  visitor: string
  hosts: string[]
  message?: string
}

export interface SetStateAction {
  type: 'set_state'
  profile: string
  state: 'working' | 'online' | 'offline' | 'thinking'
  task?: string
}

export interface BroadcastAction {
  type: 'broadcast'
  message: string
}

export interface CelebrateAction {
  type: 'celebrate'
  target: string
}

export type OfficeAction =
  | DeskVisitAction
  | DeskVisitTourAction
  | SetStateAction
  | BroadcastAction
  | CelebrateAction
