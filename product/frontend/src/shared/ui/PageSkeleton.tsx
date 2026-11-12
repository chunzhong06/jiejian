import {Heading} from './layout'
import type {ReactNode} from 'react'

const titles:Record<string,string>={'/workspace':'工作台','/permissions':'权限与覆盖','/preparation':'检查准备','/reports':'检查记录','/application':'应用与来源','/environment':'官方示例','/changes':'源码修改','/tools':'开发工具','/storage':'本地存储','/archive':'归档记录','/testing':'操作与材料','/issues':'问题与证据','/system':'运行与维护'}

/** 模块加载和业务读取共用基础页面身份；具体子任务可提供自己的标题。 */
export function pageTitle(view:string){return titles[view]??'当前工作'}

export function PageSkeleton({view='/workspace',title,navigation}:{view?:string;title?:string;navigation?:ReactNode}){
  const label=title??pageTitle(view)
  const preparation=view==='/preparation'
  return <section className="jj-page-skeleton" role="status" aria-label={'正在读取'+label} data-page-pending="true">
    <Heading title={label}/>
    {navigation}
    <div aria-hidden="true">
      <div className="jj-skeleton-toolbar"><span/><span/><span/></div>
      <div className={'jj-skeleton-surface'+(preparation?' is-preparation':'')}>
        {preparation&&<aside>{Array.from({length:5},(_,i)=><span key={i}/>)}</aside>}
        <div className="jj-skeleton-reading">{Array.from({length:3},(_,i)=><div className="jj-skeleton-row" key={i}><span/><span/></div>)}</div>
      </div>
    </div>
  </section>
}
