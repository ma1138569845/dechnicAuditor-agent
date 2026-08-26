export const knowledgeKeys = {
  all: ['knowledge'] as const,
  base: (kbId: string) => ['knowledge', 'base', kbId] as const,
  bases: ['knowledge', 'bases'] as const,
  chunks: (docId: string) => ['knowledge', 'chunks', docId] as const,
  curationJobs: (kbId: string) => ['knowledge', 'curation-jobs', kbId] as const,
  doc: (docId: string) => ['knowledge', 'doc', docId] as const,
  docs: (kbId: string, folderId: null | string, keyword: string, page: number) =>
    ['knowledge', 'docs', kbId, folderId, keyword, page] as const,
  entities: (kbId: string) => ['knowledge', 'entities', kbId] as const,
  folders: (kbId: string) => ['knowledge', 'folders', kbId] as const,
  preview: (docId: string) => ['knowledge', 'preview', docId] as const,
  relationships: (kbId: string) => ['knowledge', 'relationships', kbId] as const,
  search: (kbId: string, query: string, mode: string) => ['knowledge', 'search', kbId, query, mode] as const,
  stats: (kbId: string) => ['knowledge', 'stats', kbId] as const,
  vectorJobs: (kbId: string) => ['knowledge', 'vector-jobs', kbId] as const,
  wiki: (kbId: string, filter: string) => ['knowledge', 'wiki', kbId, filter] as const,
  wikiPage: (wikiId: string) => ['knowledge', 'wiki-page', wikiId] as const
}
