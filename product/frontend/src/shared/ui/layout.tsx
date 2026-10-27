import {cloneElement,isValidElement,useId,type ReactElement,type ReactNode} from 'react'

export function Heading({eyebrow,title,children,actions}:{eyebrow?:string;title:string;children?:ReactNode;actions?:ReactNode}){return <header className="jj-heading">{eyebrow&&<p className="jj-eyebrow">{eyebrow}</p>}<div><h1>{title}</h1>{actions&&<div className="jj-heading-actions">{actions}</div>}</div>{children&&<div className="jj-heading-note">{children}</div>}</header>}

export function Field({label,children,hint}:{label:string;children:ReactNode;hint?:string}){const id=useId(),control=isValidElement(children)?children as ReactElement<{id?:string;'aria-labelledby'?:string}>:null;return <div className="jj-field"><label id={id+'-label'} htmlFor={control?.props.id??id}>{label}</label>{control?cloneElement(control,{id:control.props.id??id,'aria-labelledby':control.props['aria-labelledby']??id+'-label'}):children}{hint&&<small>{hint}</small>}</div>}
