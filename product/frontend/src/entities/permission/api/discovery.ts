import {request} from '../../../shared/api/http'

export type DiscoveryItem={key:string;kind:'ROLE'|'ACTION'|'REQUEST';label:string;status:'PENDING'|'RELATED'|'EXCLUDED'|'RECHECK';fingerprint:string;candidate_id:string|null;action_id:string|null;source_id:string|null;request_id:string|null;in_execution?:boolean|null}
export type DiscoveryCoverage={fingerprint:string;pending_count:number;related_count:number;excluded_count:number;recheck_count:number;unexecuted_request_count?:number|null;items:DiscoveryItem[];omitted_count:number}
export const discoveryApi={current:(project:string,signal?:AbortSignal,focus?:{source_id:string;request_id:string})=>request<DiscoveryCoverage|null>(`/api/projects/${encodeURIComponent(project)}/discovery-coverage${focus?'?'+new URLSearchParams(focus):''}`,{signal})}
