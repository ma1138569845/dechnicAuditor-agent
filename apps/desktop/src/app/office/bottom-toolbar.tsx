import { useState } from 'react'
import { useStore } from '@nanostores/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { createCronJob, getCronJobs, pauseCronJob, resumeCronJob } from '@/api/cron'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { notify, notifyError } from '@/store/notifications'

import { OFFICE_GLASS } from './chrome'
import { $cronJobs } from './store'

/**
 * 底部工具栏：全部暂停/恢复（批量操作 open 的 cron 任务）+ 新建任务对话框。
 * 从 Vue OfficeBottomToolbar 移植，动作接到桌面端 cron API。
 */
export function BottomToolbar() {
  const { t } = useI18n()
  const o = t.office
  const jobs = useStore($cronJobs)
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [schedule, setSchedule] = useState('')

  const refreshJobs = async () => {
    const next = await getCronJobs()
    $cronJobs.set(next)
    await queryClient.invalidateQueries({ queryKey: ['cron'] })
  }

  const pauseAll = useMutation({
    mutationFn: async () => {
      await Promise.all(jobs.filter(job => job.enabled).map(job => pauseCronJob(job.id)))
    },
    onSuccess: async () => {
      await refreshJobs()
      notify({ kind: 'success', message: o.toolbar.paused })
    },
    onError: err => notifyError(err, o.toolbar.pauseAll)
  })
  const resumeAll = useMutation({
    mutationFn: async () => {
      await Promise.all(jobs.filter(job => !job.enabled).map(job => resumeCronJob(job.id)))
    },
    onSuccess: async () => {
      await refreshJobs()
      notify({ kind: 'success', message: o.toolbar.resumed })
    },
    onError: err => notifyError(err, o.toolbar.resumeAll)
  })
  const createTask = useMutation({
    mutationFn: () => createCronJob({ name, schedule, prompt: '' }),
    onSuccess: async () => {
      await refreshJobs()
      notify({ kind: 'success', message: o.newTask.confirm })
      setCreateOpen(false)
      setName('')
      setSchedule('')
    },
    onError: err => notifyError(err, o.newTask.title)
  })

  return (
    <div className={`inline-flex w-max max-w-full items-center gap-2 rounded-2xl px-3 py-1.5 ${OFFICE_GLASS}`}>
      <Button
        className="border-transparent bg-[color-mix(in_srgb,var(--ui-bg-elevated)_28%,transparent)] hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_48%,transparent)]"
        disabled={pauseAll.isPending}
        onClick={() => pauseAll.mutate()}
        size="sm"
        variant="secondary"
      >
        {o.toolbar.pauseAll}
      </Button>
      <Button
        className="border-transparent bg-[color-mix(in_srgb,var(--ui-bg-elevated)_28%,transparent)] hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_48%,transparent)]"
        disabled={resumeAll.isPending}
        onClick={() => resumeAll.mutate()}
        size="sm"
        variant="secondary"
      >
        {o.toolbar.resumeAll}
      </Button>
      <div className="flex-1" />
      <Button onClick={() => setCreateOpen(true)} size="sm">
        {o.toolbar.newTask}
      </Button>

      <Dialog open={createOpen} onOpenChange={value => (value ? undefined : setCreateOpen(false))}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{o.newTask.title}</DialogTitle>
            <DialogDescription>{o.rightPanel.taskFlow}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <Field htmlFor="office-task-name" label={o.newTask.name}>
              <Input
                autoFocus
                id="office-task-name"
                onChange={event => setName(event.target.value)}
                placeholder={o.newTask.namePlaceholder}
                value={name}
              />
            </Field>
            <Field htmlFor="office-task-schedule" label={o.newTask.schedule}>
              <Input
                id="office-task-schedule"
                onChange={event => setSchedule(event.target.value)}
                placeholder={o.newTask.schedulePlaceholder}
                value={schedule}
              />
            </Field>
          </div>
          <DialogFooter>
            <Button onClick={() => setCreateOpen(false)} type="button" variant="text">
              {o.newTask.cancel}
            </Button>
            <Button disabled={!name.trim() || createTask.isPending} onClick={() => createTask.mutate()} type="button">
              {o.newTask.confirm}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
