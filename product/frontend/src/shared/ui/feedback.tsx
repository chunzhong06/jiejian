import type {ReactNode} from 'react'
import {LoadingOutlined} from '@ant-design/icons'
import {Button} from './actions'

export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'positive'|'negative'|'caution'|'accent'}){return <span className={`jj-badge is-${tone}`}>{children}</span>}

export function Empty({title,children,action}:{title:string;children?:ReactNode;action?:ReactNode}){return <section className="jj-empty"><span className="jj-empty-mark" aria-hidden="true">[ ]</span><h2>{title}</h2>{children&&<p>{children}</p>}{action}</section>}

export function Loading({children='正在读取',page=false}:{children?:ReactNode;page?:boolean}){return <div className="jj-loading" role="status" data-page-pending={page||undefined}><LoadingOutlined aria-hidden="true" spin/>{children}</div>}

export function ErrorNote({error,onRetry}:{error:unknown;onRetry?:()=>void}){return <div className="jj-notice is-negative" role="alert"><span>{error instanceof Error?error.message:'请求未完成，请重新读取。'}</span>{onRetry&&<Button kind="quiet" onClick={onRetry}>重新读取</Button>}</div>}

export function Notice({children,tone='caution'}:{children:ReactNode;tone?:string}){return <div className={`jj-notice is-${tone}`} role="status">{children}</div>}
