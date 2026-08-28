import { useEffect, useRef, useState } from 'react'

import { useI18n } from '@/i18n'

import { DeskGrid, type OfficeGridProfile } from './desk-grid'
import { OfficeSceneImpl, type OfficeAgentProfile } from './engine/engine'
import type { OfficeAction } from './engine/types'

/**
 * React 壳：挂载移植的 Pixi 办公室场景；Pixi 启动失败时回退 DOM 工位网格。
 * 对父组件暴露一个 handle，供 store 直接 sync/enqueueAction/pause/resume
 * （桌面端渲染器与场景同进程，不走 HTTP 动作队列）。
 */
export interface OfficeSceneHandle {
  sync: (profiles: OfficeAgentProfile[]) => void
  enqueueAction: (action: OfficeAction) => boolean
  pause: () => void
  resume: () => void
}

export function OfficeScene({
  onAgentClick,
  onFailed,
  profiles,
  sceneRef
}: {
  onAgentClick: (payload: { name: string; clientX: number; clientY: number }) => void
  onFailed?: () => void
  profiles: OfficeAgentProfile[]
  sceneRef: React.RefObject<OfficeSceneHandle | null>
}) {
  const { t } = useI18n()
  const o = t.office
  const mountRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    let cancelled = false
    let impl: OfficeSceneImpl | null = new OfficeSceneImpl({
      visitFallback: host => `${host}`,
      ambientMessage: (visitor, host) => `${visitor} → ${host}`
    })

    const handle: OfficeSceneHandle = {
      sync: profiles => impl?.sync(profiles),
      enqueueAction: action => (impl ? impl.enqueueAction(action) : false),
      pause: () => impl?.pause(),
      resume: () => impl?.resume()
    }
    sceneRef.current = handle

    void impl.init(mount, onAgentClick).then(ok => {
      const current = impl
      if (cancelled || !current) {
        impl?.destroy()
        return
      }
      if (!ok) {
        setReady(false)
        onFailed?.()
        return
      }
      current.sync(profiles)
      current.resume()
      setReady(true)
    })

    // 主题切换时重建场景（引擎颜色在 init 时读取 CSS 变量，跟随主题）。
    const target = document.documentElement
    const observer = new MutationObserver(() => {
      if (cancelled || !impl) return
      impl.destroy()
      const fresh = new OfficeSceneImpl({
        visitFallback: host => `${host}`,
        ambientMessage: (visitor, host) => `${visitor} → ${host}`
      })
      impl = fresh
      void fresh.init(mount, onAgentClick).then(ok => {
        if (!cancelled && ok) {
          fresh.sync(profiles)
          fresh.resume()
          setReady(true)
        }
      })
    })
    observer.observe(target, { attributes: true, attributeFilter: ['class', 'data-theme'] })

    return () => {
      cancelled = true
      observer.disconnect()
      impl?.destroy()
      impl = null
      sceneRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // mount 容器常驻（effect 依赖它的尺寸）；Pixi 未就绪时 fallback 网格以
  // overlay 方式盖在其上，init 成功后移除。
  const grid: OfficeGridProfile[] = profiles.map(p => ({ name: p.name, online: p.online, busy: p.busy }))

  return (
    <div className="relative h-full min-h-0 w-full">
      <div className="absolute inset-0" ref={mountRef} />
      {!ready ? (
        <div className="absolute inset-0">
          <DeskGrid onAgentClick={onAgentClick} profiles={grid} />
        </div>
      ) : null}
    </div>
  )
}
