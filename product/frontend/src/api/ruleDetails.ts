// 单规则详情只读取指定权限修订和对应已发布结果，不以动作或最新整轮结论替代。
import {request} from './http'
export type RuleDetails = {project_id:string;intent_id:string;revision:number;current:boolean;expectation:'ALLOW'|'DENY';sentence:string;action_id:string;action_revision:number;action_label:string
  effects:Array<{effect_id:string;label:string;description:string}>;approval:{approved_at_us:number;reason:string;approved_by:string}
  preparation_complete:boolean;materials:Array<{key:string;label:string;status:string;reason_codes:string[]}>
  latest_result:null|{run_id:string;created_at_us:number;applies_to_current_implementation:boolean;cases:Array<{case_id:string;verdict:string;reason_codes:string[]}>}
  history_has_more:boolean;unreadable_history:boolean;preparation_url:string;check_url:string;history_url:string }
export const ruleDetailsApi = {read:(project:string,intent:string,revision?:number) => request<RuleDetails>(`/api/projects/${encodeURIComponent(project)}/business-boundaries/rules/${encodeURIComponent(intent)}${revision === undefined ? '' : `?revision=${revision}`}`)}
