import { assetPath } from '@/lib/asset-path'
import { cn } from '@/lib/utils'
import { useTheme } from '@/themes'

// Brand badge: the globe mark, sized via className (default size-14). The art
// is a transparent-background square, so it reads on either theme; the light
// and dark files are byte-identical today — derive both from
// `assets/appx/Wide310x150Logo.png` if the mark changes again.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  const { renderedMode } = useTheme()
  const dark = renderedMode === 'dark'

  return (
    <span className={cn('inline-flex size-14 shrink-0 items-center justify-center', className)} {...props}>
      <img alt="" className="size-full object-contain" src={assetPath(dark ? 'nous-girl-dark.png' : 'nous-girl.png')} />
    </span>
  )
}
