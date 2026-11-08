import {useEffect,useLayoutEffect,useRef,useState,type RefObject} from 'react'

type Values=Record<string,string|number|boolean>
type Position={scroll:number;focus:string;resume:boolean}
const positions=new Map<string,Position>()

/** 仅保存目录视图偏好；表单和秘密仍由各编辑器管理，不能传入这里。 */
export function useDirectoryState<T extends Values>(key:string,initial:T,ready:boolean,root:RefObject<HTMLElement|null>){
  const [value,setValue]=useState<T>(()=>{
    try{
      const saved=JSON.parse(sessionStorage.getItem(key)??'null')
      return Object.fromEntries(Object.entries(initial).map(([name,fallback])=>[name,typeof saved?.[name]===typeof fallback?saved[name]:fallback])) as T
    }catch{return initial}
  })
  const restored=useRef(false)
  useEffect(()=>{try{sessionStorage.setItem(key,JSON.stringify(value))}catch{}},[key,value])
  useLayoutEffect(()=>{
    if(!ready||restored.current)return
    restored.current=true
    const position=positions.get(key)
    if(!position?.resume)return
    const frame=requestAnimationFrame(()=>{
      // 路由先归零，再恢复目录自己的阅读位置；焦点恢复不产生额外滚动。
      window.scrollTo({top:position.scroll,behavior:'instant'})
      if(position.focus)Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[data-directory-id]')??[]).find(item=>item.dataset.directoryId===position.focus)?.focus({preventScroll:true})
      positions.set(key,{...position,resume:false})
    })
    return()=>cancelAnimationFrame(frame)
  },[key,ready,root])
  const update=(patch:Partial<T>)=>setValue(current=>({...current,...patch}))
  const remember=(focus='')=>positions.set(key,{scroll:window.scrollY,focus,resume:true})
  return {value,update,remember}
}
