import {useState} from 'react'
import {pendingProblem,savePending} from '../lib/operations'
import {scopedPath} from '../lib/navigation'
import {Notice} from './feedback'
import {ActionLink,Button} from './actions'

/** 损坏的浏览器记录不是业务失败；用户先查原记录，再决定是否移除本地副本。 */
export function PendingRecovery({storageKey,projectId,destination='/reports',label='查看检查记录'}:{storageKey:string;projectId?:string;destination?:string;label?:string}){
  const [removed,setRemoved]=useState(false)
  if(removed||!pendingProblem(storageKey))return null
  return <Notice tone="caution"><p>{pendingProblem(storageKey)}移除本地副本不会取消服务端任务。</p><div className="jj-inline-actions"><ActionLink href={'#'+scopedPath(destination,projectId)} kind="quiet">{label}</ActionLink><Button kind="quiet" onClick={()=>{savePending(storageKey,undefined);if(!pendingProblem(storageKey))setRemoved(true)}}>已核对，移除本地副本</Button></div></Notice>
}
