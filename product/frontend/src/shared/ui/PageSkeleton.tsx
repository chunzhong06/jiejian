import {Heading} from './layout'

const titles:Record<string,string>={'/workspace':'应用概览','/permissions':'权限规则','/preparation':'检查准备','/reports':'检查记录','/application':'应用连接','/environment':'官方示例','/changes':'源码修改','/tools':'开发工具','/storage':'本地存储','/archive':'归档记录'}

export function PageSkeleton({view='/workspace',title}:{view?:string;title?:string}){
  const label=title??titles[view]??'正在打开'
  const preparation=view==='/preparation'
  return <section className="jj-page-skeleton" role="status" aria-label={'正在读取'+label} data-page-pending="true">
    <Heading title={label}/>
    <div aria-hidden="true">
      <div className="jj-skeleton-toolbar"><span/><span/><span/></div>
      <div className={'jj-skeleton-surface'+(preparation?' is-preparation':'')}>
        {preparation&&<aside>{Array.from({length:5},(_,i)=><span key={i}/>)}</aside>}
        <div className="jj-skeleton-reading">{Array.from({length:3},(_,i)=><div className="jj-skeleton-row" key={i}><span/><span/></div>)}</div>
      </div>
    </div>
  </section>
}
