import { useQuery } from '@tanstack/react-query'

import { listEntities, listRelationships } from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { useI18n } from '@/i18n'

import { PanelEmpty } from '../overlays/panel'

import { knowledgeKeys } from './keys'

export function GraphTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const entitiesQuery = useQuery({
    queryFn: () => listEntities(kbId),
    queryKey: knowledgeKeys.entities(kbId)
  })
  const relationshipsQuery = useQuery({
    queryFn: () => listRelationships(kbId),
    queryKey: knowledgeKeys.relationships(kbId)
  })

  if ((entitiesQuery.isPending && !entitiesQuery.data) || (relationshipsQuery.isPending && !relationshipsQuery.data)) {
    return <PageLoader label={t.common.loading} />
  }

  const entities = entitiesQuery.data?.entities ?? []
  const relationships = relationshipsQuery.data?.relationships ?? []

  if (entities.length === 0 && relationships.length === 0) {
    return <PanelEmpty description={k.noGraphDesc} icon="search" title={k.noGraphTitle} />
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-8 overflow-y-auto px-6 pb-6 lg:grid-cols-2">
      <section>
        <h2 className="mb-3 text-sm font-medium">
          {k.entities} ({entities.length})
        </h2>
        {entities.length === 0 ? (
          <p className="text-xs text-muted-foreground">{k.noGraphDesc}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {entities.map(entity => (
              <li className="border-t border-(--ui-stroke-tertiary) pt-3 first:border-t-0 first:pt-0" key={entity.id}>
                <div className="text-sm font-medium">
                  {entity.name}
                  {entity.type ? (
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">· {entity.type}</span>
                  ) : null}
                </div>
                {entity.description ? (
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{entity.description}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2 className="mb-3 text-sm font-medium">
          {k.relationships} ({relationships.length})
        </h2>
        {relationships.length === 0 ? (
          <p className="text-xs text-muted-foreground">{k.noGraphDesc}</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {relationships.map(rel => (
              <li className="text-xs leading-relaxed" key={rel.id}>
                <span className="font-medium">{rel.source}</span>
                <span className="mx-1.5 text-muted-foreground">→ {rel.relation || 'related'} →</span>
                <span className="font-medium">{rel.target}</span>
                {rel.description ? (
                  <p className="mt-0.5 text-muted-foreground">{rel.description}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
