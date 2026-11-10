import {useEffect} from 'react'
import type {PageProps} from '../../../shared/model/page'
import {replaceDestination,returnDestination,scopedPath} from '../../../shared/lib/navigation'
import {issueDestination} from '../issueDestination'
import {Loading,Notice} from '../../../shared/ui/feedback'
import {ActionLink} from '../../../shared/ui/actions'

/** 旧权限修复链接只承接准确原题，缺失引用时不借用最近的问题。 */
export function LegacyRepairRedirect({projectId,route}:Pick<PageProps,'projectId'|'route'>){
 const fingerprint=route.query.get('repair_reference'),run=route.query.get('source_run_id'),item=route.query.get('source_case_id'),change=route.query.get('change_id'),current=route.query.get('run_id')
 const original=returnDestination(route.query.get('return_to'))??'/permissions'+(route.query.has('rule_id')?'?rule_id='+encodeURIComponent(route.query.get('rule_id')!):'')
 useEffect(()=>{if(fingerprint)replaceDestination(issueDestination({repair_fingerprint:fingerprint,...(run?{source_run_id:run}:{}),...(item?{source_case_id:item}:{})},original,{section:'repair',change_id:change,run_id:current}),projectId)},[projectId,fingerprint,run,item,change,current,original])
 return fingerprint?<Loading page/>:<Notice tone="caution">此链接缺少原问题的引用，请从原检查报告重新打开。<ActionLink href={'#'+scopedPath(original,projectId)}>返回原位置</ActionLink></Notice>
}
