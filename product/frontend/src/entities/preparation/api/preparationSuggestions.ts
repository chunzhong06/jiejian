// 材料建议与真实准备状态分开读取；保存由原Agent完成，GUI只消费精确建议修订。
import { request } from '../../../shared/api/http'
export type MaterialSuggestionKind='identity'|'execution'|'resource'|'evidence'|'recovery'
export type SuggestedMaterial=
  |{kind:'identity';account_requirement:string;slot_id?:string|null;existing_identity_ids?:string[]}
  |{kind:'execution';normal_steps:string[];entry_candidate_id?:string|null;existing_recording_ids?:string[]}
  |{kind:'resource';resource_concept:string;fields:Array<{field:string;requirement:string}>;preparation_steps:string[];existing_resource_ids?:string[]}
  |{kind:'evidence';capability:string|null;observable_result:string;field_hints:string[];existing_source_ids?:string[]}
  |{kind:'recovery';expected_state:string;entry_candidate_id?:string|null;existing_recording_ids?:string[]}
export type MaterialSuggestion={item_id:string;material:SuggestedMaterial;description:string;gap:string|null;depends_on:string[];handler:'USER'|'AGENT'|'SYSTEM';
  target:{kind:'APPROVED'|'CANDIDATE';candidate_id?:string;revision?:number};source:{classification:'SOURCE_CANDIDATE'|'HYPOTHESIS';explanation:string;candidate_ids:string[]}}
export type SuggestionItemView={item_id:string;current:boolean;reason_codes?:string[];return_url:string;resolved_target:{state:'APPROVED'|'WAITING_APPROVAL'|'ASSOCIATION_UNAVAILABLE'|'STALE';action_id:string|null;action_revision:number|null;action_label:string;actor_label?:string|null;effect_label?:string|null;candidate_id?:string;candidate_revision?:number};
  source_locations:Array<{candidate_id:string;relative_path:string;line_start:number;line_end:number;symbol:string|null}>}
export type PreparationSuggestionView={suggestion:{project_id:string;suggestion_id:string;revision:number;basis_id:string;submitted_via:'MCP'|'LOCAL_GUI';content:{items:MaterialSuggestion[];unresolved_questions:string[]}};
  state:'CURRENT'|'PARTIAL'|'STALE'|'SUPERSEDED';current_count?:number;review_count?:number;current_basis_id:string;latest_revision:number;items:SuggestionItemView[];review_url:string}
export type PreparationSuggestionContext={project_id:string;basis_id?:string;state:'CURRENT'|'NEEDS_REFRESH'|'UNAVAILABLE';latest:PreparationSuggestionView|null;note?:string}
export const preparationSuggestionsApi={show:(projectId:string,id:string,revision?:string|null)=>request<PreparationSuggestionView>(`/api/projects/${encodeURIComponent(projectId)}/proof-preparation/suggestions/${encodeURIComponent(id)}${revision==null?'':`?revision=${encodeURIComponent(revision)}`}`)}
