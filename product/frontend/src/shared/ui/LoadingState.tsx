// 等待提示与图标作为一个整体居中；页面和局部区域共用展示，不参与请求状态判断。
import { Spin } from 'antd'
import {useEffect,useState} from 'react'

export function LoadingState({ children, page = false }: { children: string; page?: boolean }) {
  const [longWait,setLongWait]=useState(false)
  useEffect(()=>{setLongWait(false);const timer=window.setTimeout(()=>setLongWait(true),15000);return()=>window.clearTimeout(timer)},[children])
  return <div className={`loading-state${page ? ' loading-state--page' : ''}`} role="status" aria-live="polite" aria-busy="true">
    <span aria-hidden="true"><Spin /></span><span>{children}</span>
    {longWait&&<span className="editorial-muted">等待时间较长，可以先返回查看其它内容。请从原操作记录查询进度，避免重复提交。</span>}
  </div>
}
