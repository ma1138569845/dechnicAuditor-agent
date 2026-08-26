import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { type KnowledgeSearchHit, type SearchMode, searchKnowledgeBase } from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'

import { PanelEmpty } from '../overlays/panel'

import { searchHitText, searchHitTitle } from './format'
import { knowledgeKeys } from './keys'

const MODES: SearchMode[] = ['vector', 'wiki', 'graph', 'unified']

export function SearchTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<SearchMode>('vector')
  const [submitted, setSubmitted] = useState('')
  const [submittedMode, setSubmittedMode] = useState<SearchMode>('vector')
  const searchQuery = useQuery({
    enabled: submitted.trim().length > 0,
    queryFn: () => searchKnowledgeBase(kbId, submitted.trim(), { limit: 12, mode: submittedMode }),
    queryKey: knowledgeKeys.search(kbId, submitted.trim(), submittedMode)
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(query.trim())
    setSubmittedMode(mode)
  }

  const results: KnowledgeSearchHit[] = searchQuery.data?.results ?? []
  const modeLabel: Record<SearchMode, string> = {
    graph: k.searchModeGraph,
    graph_wiki: k.searchModeGraph,
    unified: k.searchModeUnified,
    vector: k.searchModeVector,
    wiki: k.searchModeWiki
  }

  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-6">
      <form className="flex max-w-2xl flex-wrap items-center gap-2 pb-4" onSubmit={handleSubmit}>
        <Input
          className="min-w-48 flex-1"
          onChange={event => setQuery(event.target.value)}
          placeholder={k.searchHint}
          value={query}
        />
        <Select onValueChange={value => setMode(value as SearchMode)} value={mode}>
          <SelectTrigger className="w-36" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map(item => (
              <SelectItem key={item} value={item}>
                {modeLabel[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button disabled={!query.trim() || searchQuery.isFetching} type="submit">
          {searchQuery.isFetching ? k.searching : k.searchAction}
        </Button>
      </form>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!submitted ? (
          <PanelEmpty description={k.searchEmpty} icon="search" title={k.tabSearch} />
        ) : searchQuery.isPending ? (
          <PageLoader label={k.searching} />
        ) : results.length === 0 ? (
          <PanelEmpty description={k.searchNoResults} icon="search" title={k.searchNoResults} />
        ) : (
          <ul className="flex flex-col gap-3">
            {results.map((hit, index) => {
              const title = searchHitTitle(hit) || hit.type || k.untitled
              const text = searchHitText(hit)
              const score = typeof hit.score === 'number' ? hit.score.toFixed(3) : ''

              return (
                <li
                  className="border-t border-(--ui-stroke-tertiary) pt-3 first:border-t-0 first:pt-0"
                  key={`${title}-${index}`}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-sm font-medium">{title}</span>
                    {score ? (
                      <span className="shrink-0 tabular-nums text-[0.65rem] text-muted-foreground">
                        {k.score} {score}
                      </span>
                    ) : null}
                  </div>
                  {hit.type ? (
                    <span className="mt-0.5 block text-[0.65rem] text-muted-foreground">{hit.type}</span>
                  ) : null}
                  {text ? (
                    <p className="mt-1 line-clamp-4 text-xs leading-relaxed text-muted-foreground">{text}</p>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
