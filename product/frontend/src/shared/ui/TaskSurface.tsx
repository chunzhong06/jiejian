import {useLayoutEffect,useId,useRef,type ReactNode,type RefObject} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import {Button} from './actions'
import {Heading,TaskActions,TaskFrame} from './layout'

/** 供任务表面和自带完整导航的编辑器共用；仅在进入时聚焦，返回接续原入口。 */
export function useTaskSurfaceFocus(active:boolean,heading:RefObject<HTMLHeadingElement|null>){
  useLayoutEffect(()=>{
    if(!active)return
    const element=document.activeElement as HTMLElement|null
    const trigger=element?.closest('main')?element:null
    const top=window.scrollY,left=window.scrollX
    // 从长任务底部进入时先读新任务标题；返回仍接续原动作和阅读位置。
    window.scrollTo({top:0,left:0,behavior:'instant'})
    heading.current?.focus({preventScroll:true})
    // 卸载清理早于原正文解除 hidden，等提交后的下一帧再恢复可见入口。
    return()=>{if(trigger)requestAnimationFrame(()=>{if(trigger.isConnected&&!trigger.closest('[hidden],[inert]')){trigger.focus({preventScroll:true});window.scrollTo({top,left,behavior:'instant'})}})}
  },[active])
}

/** 聚焦任务替换原工作面；active 只控制可见与焦点，子任务继续持有草稿和后台请求；返回不表示成功或取消。 */
export function TaskSurface({title,context,status,description,headingActions,onBack,backLabel='返回原工作',backDisabled=false,children,actions,active=true,level=1,width='reading'}:{title:string;context?:ReactNode;status?:ReactNode;description?:ReactNode;headingActions?:ReactNode;onBack:()=>void;backLabel?:string;backDisabled?:boolean;children:ReactNode;actions?:ReactNode|((dismiss:()=>void)=>ReactNode);active?:boolean;level?:1|2;width?:'reading'|'wide'}){
  const id=useId(),heading=useRef<HTMLHeadingElement>(null)
  useTaskSurfaceFocus(active,heading)
  return <TaskFrame as="section" className="jj-task-surface" width={width} aria-labelledby={id} hidden={!active}>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} disabled={backDisabled} onClick={onBack}>{backLabel}</Button></div>
    <Heading eyebrow={context} title={title} status={status} id={id} titleRef={heading} level={level} actions={headingActions}>{description}</Heading>
    <div className="jj-task-surface-body">{children}</div>{actions&&<TaskActions separated>{typeof actions==='function'?actions(onBack):actions}</TaskActions>}
  </TaskFrame>
}
