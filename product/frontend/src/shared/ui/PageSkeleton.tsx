import {Heading} from './layout'
import type {ReactNode} from 'react'

const titles:Record<string,string>={'/workspace':'工作台','/permissions':'权限与覆盖','/preparation':'检查准备','/reports':'检查记录','/application':'应用与来源','/environment':'官方示例','/changes':'源码修改','/tools':'开发工具','/storage':'本地存储','/archive':'归档记录','/testing':'操作与材料','/issues':'问题与证据','/system':'运行与维护'}

/** 模块加载和业务读取共用基础页面身份；具体子任务可提供自己的标题。 */
export function pageTitle(view:string){return titles[view]??'当前工作'}

type SkeletonLayout='collection'|'directory'|'report'|'form'|'overview'

// 首屏只预留该类工作面的结构，不提前虚构对象、数量或业务状态。
const layouts:Record<string,SkeletonLayout>={'/workspace':'overview','/permissions':'collection','/preparation':'directory','/application':'form','/testing':'collection','/system':'overview','/tools':'form'}
export function PageSkeleton({view='/workspace',title,navigation,layout}:{view?:string;title?:string;navigation?:ReactNode;layout?:SkeletonLayout}){
  const label=title??pageTitle(view)
  const structure=layout??layouts[view]??'collection'
  return <section className="jj-page-skeleton" role="status" aria-label={'正在读取'+label} data-page-pending="true" data-layout={structure}>
    <Heading title={label}/>
    {navigation}
    <div aria-hidden="true">
      <div className="jj-skeleton-toolbar"><span/><span/><span/></div>
      <div className="jj-skeleton-surface">
        {structure==='directory'&&<aside><span/><span/><span/></aside>}
        <div className="jj-skeleton-reading">{Array.from({length:3},(_,i)=><div className="jj-skeleton-row" key={i}><span/><span/>{structure==='collection'&&<span/>}</div>)}</div>
        {structure==='report'&&<aside><span/><span/></aside>}
      </div>
    </div>
  </section>
}
