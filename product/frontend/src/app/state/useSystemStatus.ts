// 只读取界鉴本身的运行状态；原Agent连接由独立MCP授权状态负责。
import {useCallback,useEffect,useState} from 'react'
import {systemApi,type SystemStatus} from '../../api/system/system'
const unknownStatus:SystemStatus={api:'unknown',worker:'unknown',browser:'unknown'}
export function useSystemStatus(){
  const [status,setStatus]=useState<SystemStatus>(unknownStatus)
  const refresh=useCallback(()=>{void systemApi.status().then(setStatus).catch(()=>setStatus(unknownStatus))},[])
  useEffect(()=>{refresh();window.addEventListener('focus',refresh);return()=>window.removeEventListener('focus',refresh)},[refresh])
  return {status,refresh}
}
