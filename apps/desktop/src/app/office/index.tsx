import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useStore } from '@nanostores/react'

import { PageLoader } from '@/components/page-loader'
import { useI18n } from '@/i18n'

import { AgentActionMenu } from './agent-action-menu'
import { AgentModal } from './agent-modal'
import { BottomToolbar } from './bottom-toolbar'
import { DeskGrid } from './desk-grid'
import { HeaderStats } from './header-stats'
import { RightPanel } from './right-panel'
import type { OfficeSceneHandle } from './scene'
import {
  attachSceneEnqueue,
  detachSceneEnqueue,
  dispatchDeskVisit,
  refreshOfficeStore,
  startOfficeStore,
  stopOfficeStore,
  $activeAgent,
  $officeProfiles,
  $stats
} from './store'

const OfficeScene = lazy(async () => ({ default: (await import('./scene')).OfficeScene }))

interface ActionMenuState {
  name: string
  x: number
  y: number
}

/**
 * 虚拟办公室页面（从 hermes-studio-vue 移植）。
 *
 * 场景全幅铺底；顶栏 / 右栏 / 底栏以贴边的轻量玻璃卡片叠在场景上，
 * 不拉满高度/宽度，避免遮住工位展示区。
 */
export function OfficeView() {
  const { t } = useI18n()
  const o = t.office
  const sceneRef = useRef<OfficeSceneHandle | null>(null)
  const [sceneFailed, setSceneFailed] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [rightPanelOpen, setRightPanelOpen] = useState(false)
  const [actionMenu, setActionMenu] = useState<ActionMenuState | null>(null)
  const profiles = useStore($officeProfiles)
  const stats = useStore($stats)
  const activeAgent = useStore($activeAgent)

  useEffect(() => {
    startOfficeStore()
    attachSceneEnqueue(action => (sceneRef.current ? sceneRef.current.enqueueAction(action) : false))
    return () => {
      stopOfficeStore()
      detachSceneEnqueue()
    }
  }, [])

  const menuProfile = actionMenu ? profiles.find(p => p.name === actionMenu.name) : null
  const onlineTargets = actionMenu
    ? profiles.filter(p => p.name !== actionMenu.name).map(p => p.name)
    : []

  const handleAgentClick = (payload: { name: string; clientX: number; clientY: number }) => {
    setActionMenu({ name: payload.name, x: payload.clientX, y: payload.clientY })
  }

  const gridProfiles = profiles.map(p => ({
    name: p.name,
    label: p.label,
    online: p.online,
    busy: p.busy,
    currentWork: p.currentWork
  }))

  return (
    <div className="relative h-full min-h-0 overflow-hidden bg-(--ui-bg)">
      {/* Full-bleed scene — primary content */}
      <div className="absolute inset-0 overflow-hidden">
        <Suspense fallback={<PageLoader label={o.title} />}>
          {sceneFailed ? (
            <DeskGrid onAgentClick={handleAgentClick} profiles={gridProfiles} />
          ) : (
            <OfficeScene
              onAgentClick={handleAgentClick}
              onFailed={() => setSceneFailed(true)}
              profiles={profiles}
              sceneRef={sceneRef}
            />
          )}
        </Suspense>
      </div>

      {/* Top-left stats pill — hug content, leave center clear */}
      <div className="pointer-events-none absolute start-0 top-0 z-10 max-w-[min(36rem,calc(100%-1.5rem))] p-3">
        <div className="pointer-events-auto">
          <HeaderStats
            onRefresh={() => {
              setRefreshing(true)
              void refreshOfficeStore({ manual: true }).finally(() => setRefreshing(false))
            }}
            refreshing={refreshing}
            stats={stats}
          />
        </div>
      </div>

      {/* Top-right: collapsed by default; expands into a compact card */}
      <div className="pointer-events-none absolute end-0 top-0 z-10 max-h-[min(28rem,calc(100%-5.5rem))] p-3 ps-2">
        <div className="pointer-events-auto h-full max-h-full">
          <RightPanel onOpenChange={setRightPanelOpen} open={rightPanelOpen} />
        </div>
      </div>

      {/* Bottom-left toolbar — hug content */}
      <div className="pointer-events-none absolute bottom-0 start-0 z-10 max-w-[min(32rem,calc(100%-1.5rem))] p-3">
        <div className="pointer-events-auto">
          <BottomToolbar />
        </div>
      </div>

      <AgentModal name={activeAgent} onClose={() => $activeAgent.set(null)} />
      {actionMenu ? (
        <AgentActionMenu
          agentLabel={menuProfile?.label}
          agentName={actionMenu.name}
          onlineTargets={onlineTargets}
          onClose={() => setActionMenu(null)}
          onInteract={target => {
            dispatchDeskVisit(actionMenu.name, target, o.visitFallback)
          }}
          onOpenProfile={name => $activeAgent.set(name)}
          x={actionMenu.x}
          y={actionMenu.y}
        />
      ) : null}
    </div>
  )
}
