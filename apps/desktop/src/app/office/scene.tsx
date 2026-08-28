import { useEffect, useRef, useState } from 'react'

import { DeskGrid, type OfficeGridProfile } from './desk-grid'
import { OfficeSceneImpl, type OfficeAgentProfile } from './engine/engine'
import type { OfficeAction } from './engine/types'
import { officeSceneStrings } from './scene-strings'

/**
 * React 壳：挂载移植的 Pixi 办公室场景；Pixi 启动失败时回退 DOM 工位网格。
 * 对父组件暴露一个 handle，供 store 直接 sync/enqueueAction/pause/resume
 * （桌面端渲染器与场景同进程，不走 HTTP 动作队列）。
 */
export interface OfficeSceneHandle {
  sync: (profiles: OfficeAgentProfile[]) => void
  enqueueAction: (action: OfficeAction) => boolean
  playEmote: (name: string, animation: string) => boolean
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
  const mountRef = useRef<HTMLDivElement | null>(null)
  const implRef = useRef<OfficeSceneImpl | null>(null)
  const profilesRef = useRef(profiles)
  const onAgentClickRef = useRef(onAgentClick)
  const [ready, setReady] = useState(false)

  profilesRef.current = profiles
  onAgentClickRef.current = onAgentClick

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    let cancelled = false
    let themeTimer: ReturnType<typeof setTimeout> | null = null

    const bindHandle = (impl: OfficeSceneImpl | null) => {
      if (!impl) {
        sceneRef.current = null
        return
      }
      sceneRef.current = {
        sync: list => impl.sync(list),
        enqueueAction: action => impl.enqueueAction(action),
        playEmote: (name, animation) => impl.playEmote(name, animation),
        pause: () => impl.pause(),
        resume: () => impl.resume()
      }
    }

    const start = async () => {
      const impl = new OfficeSceneImpl(officeSceneStrings())
      implRef.current = impl
      bindHandle(impl)
      const ok = await impl.init(mount, payload => onAgentClickRef.current(payload))
      if (cancelled) {
        impl.destroy()
        if (implRef.current === impl) implRef.current = null
        return
      }
      if (!ok) {
        impl.destroy()
        implRef.current = null
        bindHandle(null)
        setReady(false)
        onFailed?.()
        return
      }
      impl.sync(profilesRef.current)
      impl.resume()
      setReady(true)
    }

    void start()

    // Theme class churn is noisy — debounce rebuilds and always sync the latest roster.
    const observer = new MutationObserver(() => {
      if (cancelled) return
      if (themeTimer) clearTimeout(themeTimer)
      themeTimer = setTimeout(() => {
        if (cancelled) return
        implRef.current?.destroy()
        implRef.current = null
        // Drop any orphaned canvases left by a raced destroy.
        mount.replaceChildren()
        void start()
      }, 80)
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-theme']
    })

    return () => {
      cancelled = true
      if (themeTimer) clearTimeout(themeTimer)
      observer.disconnect()
      implRef.current?.destroy()
      implRef.current = null
      mount.replaceChildren()
      bindHandle(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Match Vue's watch(profiles) — roster arrives after the first async refresh.
  useEffect(() => {
    if (!ready) return
    implRef.current?.sync(profiles)
  }, [profiles, ready])

  const grid: OfficeGridProfile[] = profiles.map(p => ({
    name: p.name,
    label: p.label,
    online: p.online,
    busy: p.busy
  }))

  return (
    <div className="relative h-full min-h-0 w-full overflow-hidden">
      <div className="absolute inset-0 overflow-hidden" ref={mountRef} />
      {!ready ? (
        <div className="absolute inset-0 overflow-hidden">
          <DeskGrid onAgentClick={onAgentClick} profiles={grid} />
        </div>
      ) : null}
    </div>
  )
}
