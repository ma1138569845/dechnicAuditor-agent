import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useStore } from '@nanostores/react'

import { PageLoader } from '@/components/page-loader'
import { useI18n } from '@/i18n'
import { PanelEmpty } from '../overlays/panel'

import { AgentModal } from './agent-modal'
import { BottomToolbar } from './bottom-toolbar'
import { HeaderStats } from './header-stats'
import { RightPanel } from './right-panel'
import type { OfficeSceneHandle } from './scene'
import {
  attachSceneEnqueue,
  detachSceneEnqueue,
  startOfficeStore,
  stopOfficeStore,
  $activeAgent,
  $officeProfiles,
  $stats
} from './store'

const OfficeScene = lazy(async () => ({ default: (await import('./scene')).OfficeScene }))

/**
 * 虚拟办公室页面（从 hermes-studio-vue 移植）。
 *
 * 页面挂载时启动 store 刷新 + 把场景 enqueue 桥接给 store（同进程直调）；
 * 卸载时停止刷新（场景由 OfficeScene 自身卸载销毁）。
 */
export function OfficeView() {
  const { t } = useI18n()
  const o = t.office
  const sceneRef = useRef<OfficeSceneHandle | null>(null)
  const [sceneFailed, setSceneFailed] = useState(false)
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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <HeaderStats stats={stats} />
      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1">
          <Suspense fallback={<PageLoader label={o.title} />}>
            {sceneFailed ? (
              <PanelEmpty description={o.sceneFallback.description} icon="building" title={o.sceneFallback.title} />
            ) : (
              <OfficeScene
                onAgentClick={payload => $activeAgent.set(payload.name)}
                onFailed={() => setSceneFailed(true)}
                profiles={profiles}
                sceneRef={sceneRef}
              />
            )}
          </Suspense>
        </div>
        <RightPanel />
      </div>
      <BottomToolbar />
      <AgentModal name={activeAgent} onClose={() => $activeAgent.set(null)} />
    </div>
  )
}
