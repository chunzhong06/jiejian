import {cloneElement,isValidElement,useId,type ReactElement,type ReactNode} from 'react'

export function Heading({eyebrow,title,titleIcon,children,actions,level=1}:{eyebrow?:string;title:string;titleIcon?:ReactNode;children?:ReactNode;actions?:ReactNode;level?:1|2}){const Title=level===1?'h1':'h2';return <header className="jj-heading">{eyebrow&&<p className="jj-eyebrow">{eyebrow}</p>}<div><Title>{titleIcon}{title}</Title>{actions&&<div className="jj-heading-actions">{actions}</div>}</div>{children&&<div className="jj-heading-note">{children}</div>}</header>}

// 语义层级保留对象的从属关系；视觉角色独立，避免同类集合因嵌套而变小。
export function SectionHeading({title,level=2,appearance='collection',meta,actions}:{title:string;level?:2|3;appearance?:'collection'|'group'|'caption';meta?:ReactNode;actions?:ReactNode}){
  const Title=level===2?'h2':'h3'
  return <header className="jj-section-header"><Title className={'jj-title-'+appearance}>{title}</Title>{meta&&<span>{meta}</span>}{actions&&<div className="jj-inline-actions">{actions}</div>}</header>
}

// 相邻任务按可用工作面宽度并列；各组内部保持阅读顺序，不依赖整个窗口宽度。
export function FormColumns({children}:{children:ReactNode}){
  return <div className="jj-form-columns"><div className="jj-form-columns-layout">{children}</div></div>
}

export function Field({label,children,hint}:{label:string;children:ReactNode;hint?:string}){const id=useId(),control=isValidElement(children)?children as ReactElement<{id?:string;'aria-labelledby'?:string}>:null;return <div className="jj-field"><label id={id+'-label'} htmlFor={control?.props.id??id}>{label}</label>{control?cloneElement(control,{id:control.props.id??id,'aria-labelledby':control.props['aria-labelledby']??id+'-label'}):children}{hint&&<small>{hint}</small>}</div>}
