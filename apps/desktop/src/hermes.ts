// The desktop REST/WS client, split by domain under src/api/. This module is
// the compatibility barrel: every helper keeps its historical `@/hermes`
// import path while the implementations live in focused files.
// client is the one module with internals: profileScoped / connectionScoped /
// capabilityScoped are shared across api/ but must not reach call sites, or
// request scoping stops having a single owner.
export {
  getApiRequestConnection,
  getApiRequestProfile,
  hermesApi,
  HermesGateway,
  profileScopeKey,
  PROMPT_SUBMIT_REQUEST_TIMEOUT_MS,
  setApiRequestConnection,
  setApiRequestProfile,
  STARTUP_REQUEST_TIMEOUT_MS
} from './api/client'
import { profileScoped } from './api/client'
export type { ProfileScope } from './api/client'
export * from './api/knowledge'
export * from './api/config'
export * from './api/cron'
export * from './api/mcp'
export * from './api/messaging'
export * from './api/models'
export * from './api/plugins'
export * from './api/profiles'
export * from './api/sessions'
export * from './api/skills'
export * from './api/system'
export * from './api/toolsets'

export type {
  ActionResponse,
  ActionStatusResponse,
  AnalyticsDailyEntry,
  AnalyticsModelEntry,
  AnalyticsResponse,
  AnalyticsSkillEntry,
  AnalyticsSkillsSummary,
  AnalyticsTotals,
  AudioSpeakResponse,
  AudioTranscriptionResponse,
  AutomationBlueprint,
  AutomationBlueprintField,
  AuxiliaryModelsResponse,
  BackendUpdateCheckResponse,
  ComputerUseCheck,
  ComputerUsePermissionSource,
  ComputerUseStatus,
  ConfigFieldSchema,
  ConfigSchemaResponse,
  CronDeliveryTarget,
  CronJob,
  CronJobCreatePayload,
  CronJobSchedule,
  CronJobUpdates,
  CuratorStatusResponse,
  CustomEndpoint,
  CustomEndpointsResponse,
  CustomEndpointUpdate,
  CustomEndpointValidationResponse,
  DebugShareResponse,
  ElevenLabsVoice,
  ElevenLabsVoicesResponse,
  EnvVarInfo,
  GatewayReadyPayload,
  HermesConfig,
  HermesConfigRecord,
  LogsResponse,
  McpCatalogEntry,
  McpCatalogResponse,
  McpServerSummary,
  McpServerTestResponse,
  MemoryProviderConfig,
  MemoryProviderOAuthStatus,
  MemoryStatusResponse,
  MessagingEnvVarInfo,
  MessagingHomeChannel,
  MessagingPlatformInfo,
  MessagingPlatformsResponse,
  MessagingPlatformTestResponse,
  MessagingPlatformUpdate,
  MoaConfigResponse,
  MoaModelSlot,
  ModelAssignmentRequest,
  ModelAssignmentResponse,
  ModelInfoResponse,
  ModelOptionProvider,
  ModelOptionsResponse,
  PaginatedSessions,
  PairingResponse,
  PairingUser,
  ProfileCreatePayload,
  ProfileDesktopOverlay,
  ProfileInfo,
  ProfileSetupCommand,
  ProfileSoul,
  ProfilesResponse,
  ProjectFolder,
  ProjectInfo,
  ProjectsPayload,
  RpcEvent,
  SessionCreateResponse,
  SessionInfo,
  SessionMessage,
  SessionMessagesResponse,
  SessionResumeResponse,
  SessionRuntimeInfo,
  SessionSearchResponse,
  SessionSearchResult,
  SkillHubInstalledEntry,
  SkillHubPreview,
  SkillHubResult,
  SkillHubScanResult,
  SkillHubSearchResponse,
  SkillHubSource,
  SkillHubSourcesResponse,
  SkillInfo,
  StaleAuxAssignment,
  StarmapGraph,
  StatusResponse,
  ToolsetConfig,
  ToolsetInfo,
  ToolsetModel,
  ToolsetModelsResponse,
  WebhookCreatePayload,
  WebhookCreateResponse,
  WebhookEnableResponse,
  WebhookRoute,
  WebhooksResponse
} from '@/types/hermes'

// ── Local custom APIs: Office preview & energy-audit (not in upstream) ─────
export function startOfficePreview(
  filePath: string,
  workspace?: string
): Promise<
  | { engine: string; file_id?: string; preview_base_url: string; url: string }
  | { error: string; message: string }
> {
  return window.hermesDesktop.api<
    | { engine: string; file_id?: string; preview_base_url: string; url: string }
    | { error: string; message: string }
  >({
    ...profileScoped(),
    path: '/api/office-preview/start',
    method: 'POST',
    body: { file_path: filePath, workspace }
  })
}

export function stopOfficePreview(filePath: string): Promise<{ ok: boolean }> {
  return window.hermesDesktop.api<{ ok: boolean }>({
    ...profileScoped(),
    path: '/api/office-preview/stop',
    method: 'POST',
    body: { file_path: filePath }
  })
}

export interface EnergyAuditProjectSearchResult {
  id: number
  audited_name: string
  audit_year: string | null
  reference_year: string | null
  customer_id: string | null
}

export interface EnergyAuditProjectSearchResponse {
  ok: boolean
  projects: EnergyAuditProjectSearchResult[]
  error?: string
  message?: string
}

export interface EnergyAuditGenerateResponse {
  ok: boolean
  file_path?: string
  error?: string
  message?: string
}

/** Search energy-audit projects by name, for the composer template form's
 *  autocomplete. Direct REST call — no LLM involvement. */
export function searchEnergyAuditProjects(keyword: string): Promise<EnergyAuditProjectSearchResponse> {
  return window.hermesDesktop.api<EnergyAuditProjectSearchResponse>({
    ...profileScoped(),
    path: '/api/energy-audit/projects',
    method: 'POST',
    body: { keyword }
  })
}

/** Generate an energy-audit report .docx from PG data for a project name.
 *  Returns the on-disk file path on success (for right-rail preview) or an
 *  {error, message} envelope on failure. */
export function generateEnergyAuditReport(params: {
  project_name: string
  audit_type: string
  output_dir?: string
}): Promise<EnergyAuditGenerateResponse> {
  return window.hermesDesktop.api<EnergyAuditGenerateResponse>({
    ...profileScoped(),
    path: '/api/energy-audit/generate',
    method: 'POST',
    body: params
  })
}
