/* 动作级 Workspace API：前端只渲染服务端主任务、实时实现检查和当前业务动作。 */

import type {
  BusinessActionRevisionDto,
  BusinessActorRevisionDto,
  ImplementationInspectionDto,
  PermissionBoundaryStatusDto,
  PermissionIntentRevisionDto,
} from './businessBoundaries'
import { request } from './http'

export type WorkspaceProjectDto = {
  project_id: string
  name: string
  status: 'DRAFT' | 'READY' | 'ARCHIVED'
  target_type: 'WEB'
}

export type WorkspaceConnectionDto = {
  endpoint_status: 'NEEDS_CONFIRMATION' | 'CONFIRMED' | 'UNAVAILABLE'
  source_analysis_status: 'NOT_AUTHORIZED' | 'PENDING' | 'COMPLETED'
}

export type ActorWorkspaceDto = Pick<BusinessActorRevisionDto,
  'actor_id' | 'display_name' | 'description'> & {
  actor_revision: number
  implementation: ImplementationInspectionDto & { actor_id: string; actor_revision: number }
  current_permission_reference_count: number
}

export type ActionWorkspaceDto = Pick<BusinessActionRevisionDto,
  'action_id' | 'display_name' | 'description' | 'effect_catalog'> & {
  action_revision: number
  current_permissions: PermissionIntentRevisionDto[]
  permission_status: PermissionBoundaryStatusDto
  implementation: ImplementationInspectionDto & { action_id: string; action_revision: number }
  subject_actor_ids: string[]
  actor_implementation_issue_count: number
}

export type PrimaryTaskKind =
  | 'CONFIRM_APPLICATION_ENDPOINT'
  | 'AUTHORIZE_SOURCE_ANALYSIS'
  | 'RUN_SOURCE_ANALYSIS'
  | 'REVIEW_BOUNDARY_PROPOSAL'
  | 'ESTABLISH_BUSINESS_BOUNDARY'
  | 'REVIEW_PERMISSION_REVISION'
  | 'COMPLETE_ALLOW_CONTROL'
  | 'REVIEW_ACTOR_IMPLEMENTATION'
  | 'REVIEW_ACTION_IMPLEMENTATION'
  | 'REVIEW_RECORDING'
  | 'PREPARE_TEST_IDENTITY'
  | 'DEMONSTRATE_ACTION'
  | 'PREPARE_ACTION_RESOURCE'
  | 'COMPLETE_EFFECT_EVIDENCE'
  | 'COMPLETE_RECOVERY'

export type PrimaryTaskDto = {
  task_id: string
  task_kind: PrimaryTaskKind
  business_action_id: string | null
  business_actor_id: string | null
  title: string
  why_now: string
  user_responsibility: string
  system_will_do: string
  route: '/application' | '/permissions' | '/tests'
  can_execute: boolean
  stale_fingerprint: string
  action_revision?: number | null
  identity_slot_id?: string | null
  test_identity_id?: string | null
  recording_id?: string | null
  recording_purpose?: 'TARGET' | 'OBSERVATION' | 'RECOVERY' | null
  parent_recording_id?: string | null
  effect_id?: string | null
}

export type WorkspaceAreaDto = {
  key: 'overview' | 'permissions' | 'changes' | 'tests'
  label: string
  description: string
  route: '/workspace' | '/permissions' | '/changes' | '/tests'
  status: 'READY' | 'NEEDS_ATTENTION' | 'BLOCKED'
  status_label: string
}

export type WorkspaceViewDto = {
  project: WorkspaceProjectDto
  connection: WorkspaceConnectionDto
  actors: ActorWorkspaceDto[]
  actions: ActionWorkspaceDto[]
  primary_task: PrimaryTaskDto | null
  areas: WorkspaceAreaDto[]
}

export const workspaceApi = {
  current: (projectId: string) => request<WorkspaceViewDto>(
    `/api/projects/${projectId}/workspace`,
  ),
}
