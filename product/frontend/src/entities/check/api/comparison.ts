import {request} from '../../../shared/api/http'
import type {ActionResultStory} from './currentChecks'
import type {RunEnvironment} from './routines'
import type {RepairReference} from './repairs'

export type ChangeKind='NEW'|'PERSISTING'|'FIXED'|'NO_LONGER_OBSERVED'|'RECURRED'|'UNCHANGED'|'INSUFFICIENT'|'INCOMPARABLE'
export type ComparisonRun={run_id:string;created_at_us:number;lifecycle:string;integrity:string;environment:RunEnvironment|null;source_fingerprint:string|null;deployment:'MATCHED'|'UNCONFIRMED'|'UNKNOWN'}
export type ComparisonObservation={case_id:string;verdict:string|null;expectation:string;resource_id:string;identity_status:string|null;execution_outcome:string|null;control_verdict:string|null;evidence_ids:string[]}
export type ComparisonItem={key:string;action_label:string;subject_label:string;state:ChangeKind;reasons:string[];before:ComparisonObservation|null;after:ComparisonObservation|null;verification_scope?:'SOURCE_CHANGE'|'EXTERNAL_OBSERVATION'|null;origin_repair?:RepairReference|null}
export type RunComparison={project_id:string;baseline:ComparisonRun;current:ComparisonRun;earlier:ComparisonRun|null;limitations:string[];counts:Partial<Record<ChangeKind,number>>;items:ComparisonItem[];next_cursor:string|null}
const root=(project:string)=>'/api/projects/'+encodeURIComponent(project)+'/check-comparison'
export const comparisonApi={
 read:(project:string,baseline:string,current:string,earlier?:string,after?:string,signal?:AbortSignal)=>request<RunComparison>(root(project)+'?'+new URLSearchParams({baseline,current,...(earlier?{earlier}:{}),...(after?{after}:{})}),{signal}),
 detail:(project:string,baseline:string,current:string,key:string)=>request<{project_id:string;before:ActionResultStory|null;after:ActionResultStory|null}>(root(project)+'/'+encodeURIComponent(key)+'?'+new URLSearchParams({baseline,current})),
}
