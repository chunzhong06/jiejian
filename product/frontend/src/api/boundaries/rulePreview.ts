// 规则预览是只读匹配；精确来源由后端读取，不接受浏览器自造规则正文。
import { request } from '../http'
export type RulePreviewReference = {kind:'PROPOSAL';proposal_id:string}|{kind:'APPROVED';rules:Array<{intent_id:string;revision:number}>}
export type RulePreviewSituation = {subject_id:string;owner_id:string;relation:string;action_id:string;effect_id:string}
export type RulePreview = {project_id:string;availability:'AVAILABLE'|'NEEDS_DECISION'|'STALE';coverage:null|'ALLOW'|'DENY'|'UNCOVERED'|'CONFLICT';
  actors:Array<{id:string;label:string}>;actions:Array<{id:string;label:string;effects:Array<{id:string;label:string}>}>;matches:Array<Record<string,unknown>>}
export const rulePreviewApi = {read:(projectId:string,reference:RulePreviewReference,situation?:RulePreviewSituation)=>request<RulePreview>(`/api/projects/${encodeURIComponent(projectId)}/business-boundaries/rule-preview`,{method:'POST',body:JSON.stringify({reference,situation})})}
