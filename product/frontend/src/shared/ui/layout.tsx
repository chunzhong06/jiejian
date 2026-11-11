import {cloneElement,isValidElement,useId,type HTMLAttributes,type ReactElement,type ReactNode,type Ref} from 'react'

// 图标跟随标题首行的行盒；说明增长或标题换行时，不以整个正文高度或像素偏移校准。
function TitleContent({title,icon}:{title:ReactNode;icon?:ReactNode}){return icon?<><span className="jj-heading-icon" aria-hidden="true">{icon}</span><span>{title}</span></>:title}

export function Heading({eyebrow,title,titleIcon,children,actions,level=1,id,titleRef}:{eyebrow?:ReactNode;title:string;titleIcon?:ReactNode;children?:ReactNode;actions?:ReactNode;level?:1|2;id?:string;titleRef?:Ref<HTMLHeadingElement>}){const Title=level===1?'h1':'h2';return <header className="jj-heading">{eyebrow&&<div className="jj-eyebrow">{eyebrow}</div>}<div className="jj-heading-line"><Title id={id} ref={titleRef} tabIndex={titleRef?-1:undefined} data-motion-text className={titleIcon?'jj-icon-heading':undefined}><TitleContent title={title} icon={titleIcon}/></Title>{actions&&<div className="jj-heading-actions">{actions}</div>}</div>{children&&<div className="jj-heading-note">{children}</div>}</header>}

/** 收口只安排说明与命令；业务决定动作顺序、可用条件和实际提交，不由布局推断完成。 */
export function TaskActions({children,note,separated=false,className='',...props}:HTMLAttributes<HTMLElement>&{note?:ReactNode;separated?:boolean}){
  return <footer {...props} className={'jj-task-actions '+className} data-composed data-separated={separated||undefined}>{note&&<div className="jj-action-note">{note}</div>}<div className="jj-task-commands">{children}</div></footer>
}

// 语义层级保留对象的从属关系；视觉角色独立，避免同类集合因嵌套而变小。
export function SectionHeading({title,level=2,appearance='collection',meta,actions}:{title:string;level?:2|3;appearance?:'collection'|'group'|'caption';meta?:ReactNode;actions?:ReactNode}){
  const Title=level===2?'h2':'h3'
  return <header className="jj-section-header"><Title data-motion-text className={'jj-title-'+appearance}>{title}</Title>{meta&&<span>{meta}</span>}{actions&&<div className="jj-inline-actions">{actions}</div>}</header>
}

/** 对象标题保持内部层级，装饰图标按标题首行居中；页面只安排外围留白。 */
export function ObjectHeading({title,status,caption,description,meta,icon,level=2,id}:{title:ReactNode;status?:ReactNode;caption?:ReactNode;description?:ReactNode;meta?:ReactNode;icon?:ReactNode;level?:1|2|3;id?:string}){
  const Title=level===1?'h1':level===3?'h3':'h2'
  const content=<><div className="jj-object-line"><Title id={id} data-motion-text>{title}</Title>{status}</div>{description&&<div className="jj-object-description">{description}</div>}{meta&&<div className="jj-object-meta">{meta}</div>}</>
  return icon?<div className="jj-object-heading" data-icon data-level={level}>{caption&&<p className="jj-eyebrow">{caption}</p>}<span className="jj-heading-icon" aria-hidden="true">{icon}</span><div className="jj-object-heading-copy">{content}</div></div>:<div className="jj-object-heading">{caption&&<p className="jj-eyebrow">{caption}</p>}{content}</div>
}

/** 名称和状态作为一个阅读组参与外部布局，不能被两端对齐拆到整行两侧。 */
export function ObjectIdentity({name,status}:{name:ReactNode;status:ReactNode}){
  return <span className="jj-object-identity"><span className="jj-object-name" data-motion-text>{name}</span>{status}</span>
}

// 相邻任务按可用工作面宽度并列；各组内部保持阅读顺序，不依赖整个窗口宽度。
export function FormColumns({children}:{children:ReactNode}){
  return <div className="jj-form-columns"><div className="jj-form-columns-layout">{children}</div></div>
}

export function Field({label,children,hint,error,status,hidden=false}:{label:string;children:ReactNode;hint?:string;error?:string;status?:ReactNode;hidden?:boolean}){
  const id=useId(),control=isValidElement(children)?children as ReactElement<{id?:string;'aria-labelledby'?:string;'aria-describedby'?:string;'aria-invalid'?:boolean|'true'|'false'}>:null
  const describedBy=[control?.props['aria-describedby'],hint?id+'-hint':undefined,error?id+'-error':undefined].filter(Boolean).join(' ')||undefined
  const input=control?cloneElement(control,{id:control.props.id??id,'aria-labelledby':control.props['aria-labelledby']??id+'-label','aria-describedby':describedBy,'aria-invalid':error?true:control.props['aria-invalid']}):children
  // 状态只与实际控件对齐，标签及多行说明不参与它的垂直定位。
  return <div className="jj-field" hidden={hidden} data-invalid={Boolean(error)||undefined}><label data-motion-text id={id+'-label'} htmlFor={control?.props.id??id}>{label}</label>{status?<div className="jj-field-with-status">{input}<span className="jj-field-status">{status}</span></div>:input}{hint&&<small id={id+'-hint'}>{hint}</small>}{error&&<small id={id+'-error'} className="jj-field-error" role="alert">{error}</small>}</div>
}
