import { assetPath } from '@/lib/asset-path'
import { cn } from '@/lib/utils'
import { useTheme } from '@/themes'

// Brand badge: the nous-girl mark in the app-icon squircle, theme-aware —
// light mode shows the black girl on the white squircle, dark mode the white
// girl on the #0d1117 squircle. Size via className (default size-14).
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  const { renderedMode } = useTheme()
  const dark = renderedMode === 'dark'

  return (
    <span className={cn('inline-flex size-14 shrink-0 items-center justify-center', className)} {...props}>
      <img alt="" className="size-full object-contain" src={assetPath(dark ? 'nous-girl-dark.png' : 'nous-girl.png')} />
    </span>
  )
}
