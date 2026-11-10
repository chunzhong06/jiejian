import type {RepairReference} from './api/repairs'
import {returnDestination} from '../../shared/lib/navigation'

/** 原题用完整指纹定位；任务目录编号只负责目录，不替代历史原题身份。 */
export function issueDestination(reference:Pick<RepairReference,'repair_fingerprint'>&Partial<RepairReference>,origin?:string|null,context:{section?:'repair'|'evidence';change_id?:string|null;run_id?:string|null}={}){
 const query=new URLSearchParams({repair_reference:reference.repair_fingerprint})
 if(reference.source_run_id)query.set('source_run_id',reference.source_run_id)
 if(reference.source_case_id)query.set('source_case_id',reference.source_case_id)
 if(context.section==='repair')query.set('section','repair')
 if(context.change_id)query.set('change_id',context.change_id)
 if(context.run_id)query.set('run_id',context.run_id)
 if(origin&&returnDestination(origin))query.set('return_to',origin)
 return '/issues?'+query
}
