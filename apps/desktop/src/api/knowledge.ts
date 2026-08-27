/**
 * Knowledge-base REST client — the same `/api/knowledge/*` surface the
 * hermes-studio-vue BFF proxies. Profile-aware like every other desktop REST
 * helper; no plugin namespace (that door only reaches `/api/plugins/<id>`).
 */

import { hermesApi, profileScoped } from './client'

const UPLOAD_TIMEOUT_MS = 180_000

export type DocStatus = 'completed' | 'failed' | 'pending' | 'processing'
export type SearchMode = 'graph' | 'graph_wiki' | 'unified' | 'vector' | 'wiki'
export type WikiReviewStatus = 'approved' | 'pending' | 'rejected'

export interface KbStats {
  completed: number
  failed: number
  orphaned: number
  processing: number
  total_documents: number
  total_size: number
}

export interface KnowledgeBase {
  created_at: string
  description: string
  embedding_model: null | string
  id: string
  is_system: boolean
  kb_type: string
  name: string
  qdrant_collection: string
  root_path: string
  stats?: KbStats
  updated_at: string
}

export interface KnowledgeFolder {
  created_at: string
  depth: number
  id: string
  kb_id: string
  name: string
  parent_id: null | string
  path: string
}

export interface KnowledgeDocument {
  chunk_count: number
  created_at: string
  error_message: null | string
  file_name: string
  file_path: string
  file_size: number
  file_type: string
  folder_id: null | string
  id: string
  kb_id: string
  parse_status: DocStatus
  summary_status: string
  summary_text: null | string
  title: null | string
  updated_at: string
  vector_count: number
}

export interface KnowledgeChunk {
  char_count: number
  chunk_index: number
  chunk_type: null | string
  content: string
  id: string
  is_enabled: boolean
  metadata: Record<string, unknown>
}

export interface WikiPage {
  content?: string
  doc_id?: null | string
  folder_id?: null | string
  folder_path?: string
  id: string
  kb_id?: string
  quality_report?: null | Record<string, unknown>
  quality_score?: null | number
  review_status?: string | WikiReviewStatus
  slug?: string
  source?: string
  status?: string
  title: string
  updated_at: string
}

export interface KnowledgeEntity {
  description: string
  id: string
  name: string
  type: string
}

export interface KnowledgeRelationship {
  description: string
  id: string
  relation: string
  source: string
  target: string
}

export interface KnowledgeSearchHit {
  answer?: string
  chapter?: string
  content?: string
  entities?: KnowledgeEntity[]
  filename?: string
  metadata?: Record<string, unknown>
  relationships?: KnowledgeRelationship[]
  score?: number
  text?: string
  title?: string
  type?: string
  wiki_id?: string
  [key: string]: unknown
}

export interface VectorizationJob {
  chunks_done?: number
  chunks_total?: number
  completed_at?: null | string
  created_at: string
  doc_id: string
  error?: null | string
  id: string
  kb_id: string
  progress: number
  started_at?: null | string
  status: string
}

export interface CurationJob {
  completed_at?: null | string
  created_at: string
  error_message?: null | string
  folder_id?: null | string
  id: string
  input_pages?: unknown
  job_type?: string
  kb_id: string
  output_pages?: unknown
  started_at?: null | string
  status: string
}

export interface DocPreview {
  content: string
  file_name: string
  id: string
  lines: number
  path: string
  size: number
  summary: string
}

export interface DocFilePayload {
  data?: string
  filename: string
  kind: 'binary' | 'image' | 'pdf'
  mime: string
  size: number
  too_large: boolean
}

export interface PipelineJobAck {
  doc_id?: string
  job_id?: null | string
  reason?: string
  skipped?: boolean
  status?: string
  wiki_id?: string
  [key: string]: unknown
}

export interface ListDocumentsResponse {
  documents: KnowledgeDocument[]
  page: number
  page_size: number
  total: number
}

export interface ListDocumentsQuery {
  file_type?: string
  folder_id?: string
  keyword?: string
  page?: number
  page_size?: number
  parse_status?: string
}

export interface SearchKnowledgeOptions {
  limit?: number
  mode?: SearchMode
}

function qs(params: Record<string, boolean | number | string | undefined>): string {
  const search = new URLSearchParams()

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') {
      continue
    }

    search.set(key, String(value))
  }

  const encoded = search.toString()

  return encoded ? `?${encoded}` : ''
}

function folderSegment(folderId?: null | string): string {
  return folderId ? `/folders/${encodeURIComponent(folderId)}` : ''
}

export function listKnowledgeBases(): Promise<{ bases: KnowledgeBase[] }> {
  return hermesApi({ ...profileScoped(), path: '/api/knowledge/bases' })
}

export function createKnowledgeBase(name: string, description = ''): Promise<KnowledgeBase> {
  return hermesApi({
    ...profileScoped(),
    body: { description, name },
    method: 'POST',
    path: '/api/knowledge/bases'
  })
}

export function getKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}`
  })
}

export function deleteKnowledgeBase(kbId: string): Promise<{ deleted?: boolean }> {
  return hermesApi({
    ...profileScoped(),
    method: 'DELETE',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}`
  })
}

export function listKnowledgeFolders(
  kbId: string,
  parentId?: null | string
): Promise<{ folders: KnowledgeFolder[] }> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/folders${qs({
      parent_id: parentId || undefined
    })}`
  })
}

export async function listAllKnowledgeFolders(kbId: string): Promise<KnowledgeFolder[]> {
  const { folders } = await hermesApi<{ folders: KnowledgeFolder[] }>({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/folders${qs({ all: true })}`
  })

  return folders
}

export function createKnowledgeFolder(
  kbId: string,
  name: string,
  parentId?: null | string
): Promise<KnowledgeFolder> {
  return hermesApi({
    ...profileScoped(),
    body: { name, parent_id: parentId || null },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/folders`
  })
}

export function deleteKnowledgeFolder(kbId: string, folderId: string): Promise<{ deleted?: boolean }> {
  return hermesApi({
    ...profileScoped(),
    method: 'DELETE',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}`
  })
}

export function listKnowledgeDocuments(kbId: string, query: ListDocumentsQuery = {}): Promise<ListDocumentsResponse> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/docs${qs({
      file_type: query.file_type,
      folder_id: query.folder_id,
      keyword: query.keyword,
      page: query.page,
      page_size: query.page_size,
      parse_status: query.parse_status
    })}`
  })
}

export function getKnowledgeDocument(docId: string): Promise<KnowledgeDocument> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}`
  })
}

export function getDocumentPreview(docId: string): Promise<DocPreview> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/preview`
  })
}

export function getDocumentFilePayload(docId: string): Promise<DocFilePayload> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/file-payload`
  })
}

export function deleteKnowledgeDocument(kbId: string, docId: string): Promise<{ deleted?: boolean }> {
  return hermesApi({
    ...profileScoped(),
    method: 'DELETE',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/docs/${encodeURIComponent(docId)}`
  })
}

export function bulkDeleteDocuments(
  kbId: string,
  docIds: string[]
): Promise<{ deleted: number; failed: number }> {
  return hermesApi({
    ...profileScoped(),
    body: { doc_ids: docIds },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/bulk-delete`
  })
}

export async function uploadKnowledgeDocument(
  kbId: string,
  file: { bytes: ArrayBuffer; contentType?: string; filename: string },
  folderId?: null | string
): Promise<KnowledgeDocument> {
  const data = await hermesApi<
    KnowledgeDocument | { document?: KnowledgeDocument; existing?: KnowledgeDocument }
  >({
    ...profileScoped(),
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/docs/upload${qs({
      folder_id: folderId || undefined
    })}`,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    upload: file
  })

  if (data && typeof data === 'object') {
    if ('document' in data && data.document) {
      return data.document
    }

    if ('existing' in data && data.existing) {
      return data.existing
    }
  }

  return data as KnowledgeDocument
}

export function listDocumentChunks(docId: string): Promise<{ chunks: KnowledgeChunk[] }> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/chunks`
  })
}

export function updateChunk(
  chunkId: string,
  patch: { content?: string; is_enabled?: boolean }
): Promise<{ chunks: KnowledgeChunk[] }> {
  return hermesApi({
    ...profileScoped(),
    body: patch,
    method: 'PATCH',
    path: `/api/knowledge/chunks/${encodeURIComponent(chunkId)}`
  })
}

export function deleteChunk(chunkId: string): Promise<{ chunks?: KnowledgeChunk[]; deleted?: boolean }> {
  return hermesApi({
    ...profileScoped(),
    method: 'DELETE',
    path: `/api/knowledge/chunks/${encodeURIComponent(chunkId)}`
  })
}

export function startVectorize(docId: string): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    method: 'POST',
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/vectorize`
  })
}

export function generateSummary(docId: string): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    method: 'POST',
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/summary`
  })
}

export function buildGraph(docId: string): Promise<{ entities?: number; id: string; relationships?: number; status?: string }> {
  return hermesApi({
    ...profileScoped(),
    method: 'POST',
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/graph`
  })
}

export function generateDocWiki(docId: string, curate = false): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    body: { curate },
    method: 'POST',
    path: `/api/knowledge/docs/${encodeURIComponent(docId)}/wiki`
  })
}

export function rebuildKnowledgeBase(
  kbId: string
): Promise<{ kb_id: string; queued_documents: number; rebuild_jobs: string[] }> {
  return hermesApi({
    ...profileScoped(),
    body: {},
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/rebuild`
  })
}

export function startBulkWiki(
  kbId: string,
  opts?: { docIds?: string[]; folderId?: null | string }
): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    body: { doc_ids: opts?.docIds || null },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}${folderSegment(opts?.folderId)}/bulk-wiki`
  })
}

export function startHierarchicalWiki(
  kbId: string,
  opts?: { curate?: boolean; folderId?: null | string }
): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    body: { curate: Boolean(opts?.curate) },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}${folderSegment(opts?.folderId)}/hierarchical-wiki`
  })
}

export function startCuration(
  kbId: string,
  opts?: { folderId?: null | string; pageIds?: string[]; reviewStatus?: string }
): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    body: {
      page_ids: opts?.pageIds || null,
      review_status: opts?.reviewStatus || null
    },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}${folderSegment(opts?.folderId)}/curate`
  })
}

export function generateFolderWiki(
  kbId: string,
  folderId: null | string,
  opts?: { curate?: boolean; title?: string }
): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    body: { curate: Boolean(opts?.curate), title: opts?.title || '' },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId || 'root')}/wiki`
  })
}

export function getVectorizationJob(jobId: string): Promise<VectorizationJob> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/jobs/${encodeURIComponent(jobId)}`
  })
}

export function listVectorizationJobs(kbId: string): Promise<{ jobs: VectorizationJob[] }> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/vectorization-jobs`
  })
}

export function listCurationJobs(kbId: string): Promise<{ jobs: CurationJob[] }> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/curation-jobs`
  })
}

export function searchKnowledgeBase(
  kbId: string,
  query: string,
  opts: SearchKnowledgeOptions = {}
): Promise<{ results: KnowledgeSearchHit[] }> {
  return hermesApi({
    ...profileScoped(),
    body: { limit: opts.limit ?? 10, mode: opts.mode ?? 'vector', query },
    method: 'POST',
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/search`
  })
}

export function listKnowledgeWiki(
  kbId: string,
  opts?: { review_status?: string }
): Promise<{ pages: WikiPage[] }> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/wiki${qs({
      review_status: opts?.review_status
    })}`
  })
}

export function getWikiPage(wikiId: string): Promise<WikiPage> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/wiki/${encodeURIComponent(wikiId)}`
  })
}

export function updateWikiReview(
  wikiId: string,
  reviewStatus: WikiReviewStatus
): Promise<{ id: string; review_status: string }> {
  return hermesApi({
    ...profileScoped(),
    body: { review_status: reviewStatus },
    method: 'PATCH',
    path: `/api/knowledge/wiki/${encodeURIComponent(wikiId)}/review`
  })
}

export function evaluateWikiQuality(wikiId: string): Promise<PipelineJobAck> {
  return hermesApi({
    ...profileScoped(),
    method: 'POST',
    path: `/api/knowledge/wiki/${encodeURIComponent(wikiId)}/evaluate-quality`
  })
}

export function listEntities(kbId: string, topK = 100): Promise<{ entities: KnowledgeEntity[] }> {
  const limit = Math.max(1, Math.floor(topK))

  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/entities?top_k=${limit}`
  })
}

export function listRelationships(
  kbId: string,
  topK = 200
): Promise<{ relationships: KnowledgeRelationship[] }> {
  const limit = Math.max(1, Math.floor(topK))

  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/relationships?top_k=${limit}`
  })
}

export function getKnowledgeStats(kbId: string): Promise<KbStats> {
  return hermesApi({
    ...profileScoped(),
    path: `/api/knowledge/bases/${encodeURIComponent(kbId)}/stats`
  })
}
