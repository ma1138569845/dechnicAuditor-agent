import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

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
import { newSessionInProfile } from '@/store/profile'

import { agentCssColor, agentTextCssColor } from './engine/theme'

/**
 * Agent 详情弹窗（点击场景角色打开）：soul / skills 页签 + 聊天入口。
 * memory 页签为占位（desktop 无对应端点）。
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
  const [tab, setTab] = useState('soul')

  const soulQuery = useQuery({
    enabled: Boolean(name),
    queryFn: () => getProfileSoul(name!),
    queryKey: ['office', 'soul', name],
    retry: false
  })
  const skillsQuery = useQuery({
    enabled: Boolean(name),
    queryFn: () => getSkills(name ?? undefined),
    queryKey: ['office', 'skills', name],
    retry: false
  })

  return (
    <Dialog open={Boolean(name)} onOpenChange={value => (!value ? onClose() : undefined)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-full text-[0.7rem] font-bold"
              style={
                name
                  ? { background: agentCssColor(name), color: agentTextCssColor(name) }
                  : undefined
              }
            >
              {name ? (name.trim()[0]?.toUpperCase() ?? '?') : '?'}
            </span>
            {name}
          </DialogTitle>
          <DialogDescription>{o.agentModal.config}</DialogDescription>
        </DialogHeader>

        <Tabs onValueChange={setTab} value={tab}>
          <TabsList>
            <TabsTrigger value="soul">{o.agentModal.soul}</TabsTrigger>
            <TabsTrigger value="skills">{o.agentModal.skills}</TabsTrigger>
          </TabsList>
          <div className="max-h-64 min-h-24 overflow-y-auto px-1 py-3">
            {tab === 'soul' ? (
              <div data-slot="tab-soul">
                {soulQuery.isLoading ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{t.common.loading}</p>
                ) : soulQuery.error || !soulQuery.data ? (
                  <p className="text-xs text-(--ui-text-tertiary)">{o.agentModal.memoryEmpty}</p>
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-(--ui-text-primary)">
                    {soulQuery.data.content ?? ''}
                  </pre>
                )}
              </div>
            ) : (
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
            )}
          </div>
        </Tabs>

        <DialogFooter>
          <Button onClick={onClose} type="button" variant="text">
            {t.common.close}
          </Button>
          <Button
            onClick={() => {
              if (name) newSessionInProfile(name)
            }}
            type="button"
          >
            {o.agentModal.openChat}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
