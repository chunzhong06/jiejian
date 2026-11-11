import type {HTMLAttributes,ReactNode} from 'react'
import LoadingOutlined from '@ant-design/icons/LoadingOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import {Heading} from './layout'
import {ApiError} from '../api/http'

export type FeedbackTone='neutral'|'positive'|'negative'|'caution'|'accent'

export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:FeedbackTone}){return <span className={`jj-badge is-${tone}`}>{children}</span>}

export function Status({children,tone='neutral',className='',...props}:HTMLAttributes<HTMLSpanElement>&{tone?:FeedbackTone}){return <span {...props} data-tone={tone} className={`jj-status is-${tone} ${className}`}>{children}</span>}

/** 一项核验属性与已知状态相邻；业务调用方提供状态，不从说明或请求成败推断结论。 */
export function ResultSummary({label,status}:{label:ReactNode;status:ReactNode}){return <div className="jj-result-summary"><span className="jj-result-label">{label}</span>{status}</div>}

/** 成组核对结果按可用宽度排列，名称与自身状态保持相邻；状态仍由业务提供。 */
export function ResultList({items,label}:{items:Array<{label:ReactNode;status:ReactNode}>;label:string}){return <div className="jj-result-overview" role="list" aria-label={label}>{items.map((item,index)=><div role="listitem" key={index}><ResultSummary {...item}/></div>)}</div>}

/** 已有页面标题或分类边界时使用 section，沿当前内容轴呈现，不再次居中整组内容。 */
export function Empty({title,children,action,layout='page'}:{title:string;children?:ReactNode;action?:ReactNode;layout?:'page'|'section'}){return <section className="jj-empty" data-layout={layout}><div className="jj-empty-copy"><h2>{title}</h2>{children&&<p>{children}</p>}</div>{action&&<div className="jj-empty-actions">{action}</div>}</section>}

export function Loading({children='正在读取',page=false}:{children?:ReactNode;page?:boolean}){return <div className="jj-loading" role="status" data-page-pending={page||undefined}><LoadingOutlined aria-hidden="true" spin/>{children}</div>}

export function ErrorNote({error}:{error:unknown}){return <div className="jj-notice is-negative" role="alert"><span>{error instanceof Error?error.message:'请求未完成，可通过右上角刷新重新读取。'}</span>{error instanceof ApiError&&error.traceId&&<small className="jj-small">诊断编号：{error.traceId}</small>}</div>}

export function PageError({title,error}:{title:string;error:unknown}){
  return <section className="jj-page-state"><Heading title={title}/><div className="jj-page-state-content"><span className="jj-page-state-icon" aria-hidden="true"><ExclamationCircleOutlined/></span><div><h2>当前内容未能读取</h2><p>请根据下面的原因处理，再使用右上角刷新重试。</p><ErrorNote error={error}/></div></div></section>
}

/** 长期需要核对的原因与恢复动作成组；普通简短消息仍保留行内表达。 */
export function Notice({children,tone='neutral',title,actions}:{children?:ReactNode;tone?:FeedbackTone;title?:string;actions?:ReactNode}){return <div className={`jj-notice is-${tone}`} role="status">{title||actions?<><div className="jj-notice-copy">{title&&<strong>{title}</strong>}{children&&<div>{children}</div>}</div>{actions&&<div className="jj-notice-actions">{actions}</div>}</>:children}</div>}

/** 解释已知事实的适用范围；需要用户处理的异常仍用 Notice 呈现。 */
export function ContextNote({children,label}:{children:ReactNode;label:string}){return <aside className="jj-context-note" aria-label={label}>{children}</aside>}

/** 已发生的完成反馈留在原操作附近，不与需要处理的持续警告争夺视觉重量。 */
export function InlineFeedback({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'positive'}){return <p className="jj-inline-feedback" data-tone={tone} role="status">{children}</p>}
