import {useEffect,useRef} from 'react'

type Reader=()=>unknown|Promise<unknown>
const readers=new Set<Reader>()
let pending:Promise<void>|undefined

export function subscribePageRefresh(read:Reader){
  readers.add(read)
  return()=>{readers.delete(read)}
}

/** 只调用当前挂载工作面的读取所有者；并发点击共享本次刷新，不重新挂载页面或重放写请求。 */
export function refreshCurrentPage(){
  if(pending)return pending
  pending=Promise.allSettled([...readers].map(async read=>read())).then(()=>undefined).finally(()=>{pending=undefined})
  return pending
}

/** 非 useRead 的读取所有者在此接入，回调须保留自身的忙碌、归属与失效响应保护。 */
export function usePageRefresh(read:Reader,enabled=true){
  const latest=useRef(read);latest.current=read
  useEffect(()=>enabled?subscribePageRefresh(()=>latest.current()):undefined,[enabled])
}
