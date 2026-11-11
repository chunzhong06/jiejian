import {useEffect,useId,useRef,type ReactNode} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import {Button} from './actions'
import {Heading,TaskActions} from './layout'

/** 聚焦任务替换原工作面；active 只控制可见与焦点，子任务继续持有草稿和后台请求；返回不表示成功或取消。 */
export function TaskSurface({title,context,description,onBack,backLabel='返回原工作',children,actions,active=true,level=1,width='reading'}:{title:string;context?:ReactNode;description?:ReactNode;onBack:()=>void;backLabel?:string;children:ReactNode;actions?:ReactNode|((dismiss:()=>void)=>ReactNode);active?:boolean;level?:1|2;width?:'reading'|'wide'}){
  const id=useId(),heading=useRef<HTMLHeadingElement>(null)
  useEffect(()=>{if(!active)return;const trigger=document.activeElement as HTMLElement|null;heading.current?.focus({preventScroll:true});return()=>{if(trigger?.isConnected)trigger.focus({preventScroll:true})}},[active])
  return <section className="jj-task-surface" data-width={width} aria-labelledby={id} hidden={!active}>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>{backLabel}</Button></div>
    <Heading eyebrow={context} title={title} id={id} titleRef={heading} level={level}>{description}</Heading>
    <div className="jj-task-surface-body">{children}</div>{actions&&<TaskActions separated>{typeof actions==='function'?actions(onBack):actions}</TaskActions>}
  </section>
}
