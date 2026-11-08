import type {HTMLAttributes,ReactNode} from 'react'
import LoadingOutlined from '@ant-design/icons/LoadingOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import {Heading} from './layout'

export type FeedbackTone='neutral'|'positive'|'negative'|'caution'|'accent'

export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:FeedbackTone}){return <span className={`jj-badge is-${tone}`}>{children}</span>}

export function Status({children,tone='neutral',className='',...props}:HTMLAttributes<HTMLSpanElement>&{tone?:FeedbackTone}){return <span {...props} data-tone={tone} className={`jj-status is-${tone} ${className}`}>{children}</span>}

/** 一项核验属性与已知状态相邻；业务调用方提供状态，不从说明或请求成败推断结论。 */
export function ResultSummary({label,status}:{label:ReactNode;status:ReactNode}){return <div className="jj-result-summary"><span className="jj-result-label">{label}</span>{status}</div>}

/** 成组核对结果按可用宽度排列，名称与自身状态保持相邻；状态仍由业务提供。 */
export function ResultList({items,label}:{items:Array<{label:ReactNode;status:ReactNode}>;label:string}){return <div className="jj-result-overview" role="list" aria-label={label}>{items.map((item,index)=><div role="listitem" key={index}><ResultSummary {...item}/></div>)}</div>}

export function Empty({title,children,action}:{title:string;children?:ReactNode;action?:ReactNode}){return <section className="jj-empty"><div className="jj-empty-copy"><h2>{title}</h2>{children&&<p>{children}</p>}</div>{action&&<div className="jj-empty-actions">{action}</div>}</section>}

export function Loading({children='正在读取',page=false}:{children?:ReactNode;page?:boolean}){return <div className="jj-loading" role="status" data-page-pending={page||undefined}><LoadingOutlined aria-hidden="true" spin/>{children}</div>}

export function ErrorNote({error}:{error:unknown}){return <div className="jj-notice is-negative" role="alert"><span>{error instanceof Error?error.message:'请求未完成，可通过右上角刷新重新读取。'}</span></div>}

export function PageError({title,error}:{title:string;error:unknown}){
  return <section className="jj-page-state"><Heading title={title}/><div className="jj-page-state-content"><span className="jj-page-state-icon" aria-hidden="true"><ExclamationCircleOutlined/></span><div><h2>当前内容未能读取</h2><p>已保存的资料保留。处理下面的原因后，可使用右上角刷新继续工作。</p><ErrorNote error={error}/></div></div></section>
}

export function Notice({children,tone='neutral'}:{children:ReactNode;tone?:FeedbackTone}){return <div className={`jj-notice is-${tone}`} role="status">{children}</div>}
