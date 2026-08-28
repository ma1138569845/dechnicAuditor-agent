import { useStore } from '@nanostores/react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { pluginRest } from '@/api/plugins'
import { getProfileSoul } from '@/api/profiles'
import { getSkills } from '@/api/skills'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useI18n } from '@/i18n'
import { $profiles, newSessionInProfile, profileLabel } from '@/store/profile'

import { tasksForAgent, type OfficeKanbanBoard } from './agent-tasks'
import { avatarInitial } from './avatar-initial'
import { agentCssColor, agentTextCssColor } from './engine/theme'
import { StatusBadge } from './status-badge'
import { $officeProfiles } from './store'

type ModalTab = 'soul' | 'skills' | 'memory' | 'tasks' | 'archive'

/**
 * Agent 详情弹窗：对齐 Vue OfficeAgentModal 的页签结构。
 * - 灵魂 / 技能：已接桌面 API
 * - 记忆：桌面端尚无 MEMORY.md / USER.md 正文接口，诚实空态
 * - 任务 / 归档：读 Kanban 看板（插件不可用时显示空态）
 * - 打开聊天放在底部按钮，不占独立页签
 */
export function AgentModal({
  name,
  onClose
}: {
  name: string | null
  onClose: () => void
}) {
  const { t } = useI18n()
  const o = t.office
  const navigate = useNavigate()
  const [tab, setTab] = useState<ModalTab>('soul')
  const profiles = useStore($profiles)
  const officeProfiles = useStore($officeProfiles)
  const profile = name ? profiles.find(item => item.name === name) : null
  const sceneProfile = name ? officeProfiles.find(item => item.name === name) : null
  const displayName = profile ? profileLabel(profile) : name ?? ''
  const isBusy = sceneProfile?.busy === true
  const gatewayRunning = sceneProfile?.online === true

  useEffect(() => {
    setTab('soul')
  }, [name])

  const soulQuery = useQuery({
    enabled: Boolean(name),
    queryFn: () => getProfileSoul(name!),
    queryKey: ['office', 'soul', name],
    retry: false
  })
  const skillsQuery = useQuery({
    enabled: Boolean(name) && (tab === 'skills' || tab === 'soul'),
    queryFn: () => getSkills(name ?? undefined),
    queryKey: ['office', 'skills', name],
    retry: false
  })
  const boardQuery = useQuery({
    enabled: Boolean(name) && (tab === 'tasks' || tab === 'archive'),
    queryFn: () => pluginRest<OfficeKanbanBoard>('kanban', '/board?include_archived=true'),
    queryKey: ['office', 'kanban-board', name],
    retry: false
  })

  const activeTasks = tasksForAgent(boardQuery.data, name ?? '', 'active')
  const archivedTasks = tasksForAgent(boardQuery.data, name ?? '', 'archived')

  const openChat = () => {
    if (name) newSessionInProfile(name)
  }

  const openKanban = (taskId: string) => {
    onClose()
    void navigate(`/kanban?task=${encodeURIComponent(taskId)}`)
  }

  return (
    <Dialog open={Boolean(name)} onOpenChange={value => (!value ? onClose() : undefined)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 pe-8">
            <span
              className="flex h-7 w-7 items-center justify-center rounded-full text-[0.75rem] font-bold"
              style={
                name
                  ? { background: agentCssColor(name), color: agentTextCssColor(name) }
                  : undefined
              }
            >
              {displayName ? avatarInitial(displayName) : '?'}
            </span>
            <span className="min-w-0 flex-1 truncate">{displayName}</span>
          </DialogTitle>
          <DialogDescription className="flex flex-col items-start gap-2">
            <div className="flex flex-wrap items-start gap-3">
              <span className="pt-1">{o.agentModal.config}</span>
              <StatusBadge busy={isBusy} gatewayRunning={gatewayRunning} showHint />
            </div>
            {isBusy && sceneProfile?.currentWork ? (
              <p className="text-xs text-(--ui-yellow)">
                {o.agentModal.workingOn}: {sceneProfile.currentWork}
              </p>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        <Tabs onValueChange={value => setTab(value as ModalTab)} value={tab}>
          <TabsList className="h-auto w-full flex-wrap justify-start">
            <TabsTrigger value="soul">{o.agentModal.soul}</TabsTrigger>
            <TabsTrigger value="skills">{o.agentModal.skills}</TabsTrigger>
            <TabsTrigger value="memory">{o.agentModal.memory}</TabsTrigger>
            <TabsTrigger value="tasks">{o.agentModal.tasks}</TabsTrigger>
            <TabsTrigger value="archive">{o.agentModal.archive}</TabsTrigger>
          </TabsList>
          <div className="max-h-72 min-h-28 overflow-y-auto px-1 py-3">
            {tab === 'soul' ? (
              <div data-slot="tab-soul">
                {soulQuery.isLoading ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{t.common.loading}</p>
                ) : soulQuery.error ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.soulLoadFailed}</p>
                ) : !soulQuery.data?.content?.trim() ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.soulEmpty}</p>
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-(--ui-text-primary)">
                    {soulQuery.data.content}
                  </pre>
                )}
              </div>
            ) : null}

            {tab === 'skills' ? (
              <div data-slot="tab-skills">
                {skillsQuery.isLoading ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{t.common.loading}</p>
                ) : skillsQuery.data?.length ? (
                  <ul className="flex flex-col gap-1">
                    {skillsQuery.data.map(skill => (
                      <li className="text-xs text-(--ui-text-primary)" key={skill.name}>
                        {skill.name}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.skillsEmpty}</p>
                )}
              </div>
            ) : null}

            {tab === 'memory' ? (
              <div className="flex flex-col gap-4" data-slot="tab-memory">
                <section>
                  <h3 className="mb-1.5 text-xs font-medium text-(--ui-text-primary)">
                    {o.agentModal.notes}
                  </h3>
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.memoryEmpty}</p>
                </section>
                <section>
                  <h3 className="mb-1.5 text-xs font-medium text-(--ui-text-primary)">
                    {o.agentModal.userProfile}
                  </h3>
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.userEmpty}</p>
                </section>
              </div>
            ) : null}

            {tab === 'tasks' ? (
              <div data-slot="tab-tasks">
                {boardQuery.isLoading ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{t.common.loading}</p>
                ) : activeTasks.length ? (
                  <ul className="flex flex-col gap-0.5">
                    {activeTasks.map(task => (
                      <li key={task.id}>
                        <button
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-xs hover:bg-(--ui-row-hover-background) focus-visible:outline-none"
                          onClick={() => openKanban(task.id)}
                          type="button"
                        >
                          <span className="min-w-0 flex-1 truncate text-(--ui-text-primary)">
                            {task.title?.trim() || task.id}
                          </span>
                          <span className="shrink-0 text-[0.65rem] text-(--ui-text-tertiary)">
                            {task.status}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.tasksEmpty}</p>
                )}
              </div>
            ) : null}

            {tab === 'archive' ? (
              <div data-slot="tab-archive">
                {boardQuery.isLoading ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{t.common.loading}</p>
                ) : archivedTasks.length ? (
                  <ul className="flex flex-col gap-0.5">
                    {archivedTasks.map(task => (
                      <li key={task.id}>
                        <button
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-xs hover:bg-(--ui-row-hover-background) focus-visible:outline-none"
                          onClick={() => openKanban(task.id)}
                          type="button"
                        >
                          <span className="min-w-0 flex-1 truncate text-(--ui-text-primary)">
                            {task.title?.trim() || task.id}
                          </span>
                          <span className="shrink-0 text-[0.65rem] text-(--ui-text-tertiary)">
                            {task.status}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.archiveEmpty}</p>
                )}
              </div>
            ) : null}
          </div>
        </Tabs>

        <DialogFooter>
          <Button onClick={onClose} type="button" variant="text">
            {t.common.close}
          </Button>
          <Button onClick={openChat} type="button">
            {o.agentModal.openChat}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
