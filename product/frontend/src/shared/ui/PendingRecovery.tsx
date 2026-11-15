import {useState} from 'react'
import {pendingProblem,savePending} from '../lib/operations'
import {scopedPath} from '../lib/navigation'
import {Notice} from './feedback'
import {ActionLink,Button} from './actions'

/** 损坏的浏览器记录不是业务失败；用户先查原记录，再决定是否移除本地副本。 */
export function PendingRecovery({storageKey,projectId,destination='/reports',label='查看检查记录'}:{storageKey:string;projectId?:string;destination?:string;label?:string}){
  const [removed,setRemoved]=useState(false)
  if(removed||!pendingProblem(storageKey))return null
  return <Notice tone="caution" title="先核对原任务记录" actions={<ActionLink kind="default" href={'#'+scopedPath(destination,projectId)}>{label}</ActionLink>}><p>{pendingProblem(storageKey)}</p><details><summary>已核对原记录？</summary><p>可移除损坏的本地副本，服务端原任务继续保留。</p><Button kind="quiet" onClick={()=>{savePending(storageKey,undefined);if(!pendingProblem(storageKey))setRemoved(true)}}>已核对，移除本地副本</Button></details></Notice>
}
