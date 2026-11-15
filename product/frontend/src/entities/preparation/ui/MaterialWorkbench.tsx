import type {ReactNode,Ref} from 'react'
import UserOutlined from '@ant-design/icons/UserOutlined'
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined'
import DatabaseOutlined from '@ant-design/icons/DatabaseOutlined'
import FileDoneOutlined from '@ant-design/icons/FileDoneOutlined'
import UndoOutlined from '@ant-design/icons/UndoOutlined'
import DownOutlined from '@ant-design/icons/DownOutlined'
import type {PreparationItem} from '../api/preparation'
import {Button} from '../../../shared/ui/actions'
import {Badge} from '../../../shared/ui/feedback'
import {ObjectHeading,SectionHeading} from '../../../shared/ui/layout'
import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {CommandMenu} from '../../../shared/ui/CommandMenu'
import './material-workbench.css'

export const materialNames={identity:'测试账号',execution:'操作流程',resource:'测试资源',evidence:'业务结果证明',recovery:'操作恢复'}
export type MaterialKind=keyof typeof materialNames
const icons={identity:<UserOutlined/>,execution:<VideoCameraOutlined/>,resource:<DatabaseOutlined/>,evidence:<FileDoneOutlined/>,recovery:<UndoOutlined/>}

/** 展示原材料状态，不计算计划是否可执行；执行门禁继续由预览服务拥有。 */
export function materialStatus(items:PreparationItem[]){
 if(!items.length)return {label:'没有要求',tone:'neutral' as const}
 if(items.every(item=>item.status==='NOT_REQUIRED'))return {label:'不需要',tone:'neutral' as const}
 if(items.every(item=>['SATISFIED','NOT_REQUIRED'].includes(item.status)))return {label:'已就绪',tone:'positive' as const}
 if(items.some(item=>item.status==='BLOCKED'))return {label:'需要处理',tone:'caution' as const}
 if(items.some(item=>item.status==='STALE'))return {label:'需重新核对',tone:'neutral' as const}
 return {label:'待准备',tone:'neutral' as const}
}

/** 普通材料维护与检查内准备共用任务骨架，页面保留读取、草稿及命令所有权。 */
export function MaterialWorkbench({actions,actionId,onActionChange,materials,selected,onSelect,children,footer,disabled=false,containerRef,hidden=false}:{
 actions:Array<{id:string;label:string;complete:boolean}>;actionId:string;onActionChange:(id:string)=>void
 materials:Array<{kind:MaterialKind;items:PreparationItem[]}>;selected:MaterialKind;onSelect:(kind:MaterialKind)=>void
 children:ReactNode;footer?:ReactNode;disabled?:boolean;containerRef?:Ref<HTMLElement>;hidden?:boolean
}){
 const action=actions.find(item=>item.id===actionId)
 if(!action)return null
 return <section ref={containerRef} hidden={hidden} className="jj-material-workbench" aria-label="当前业务操作所需材料">
  <header className="jj-material-workbench-context" data-milestone-part="heading">
   <ObjectHeading level={2} title={action.label} status={<Badge tone={action.complete?'positive':'neutral'}>{action.complete?'材料齐备':'材料待核对'}</Badge>}/>
   {actions.length>1&&<CommandMenu menu={{items:actions.map(item=>({key:item.id,label:item.label})),selectedKeys:[action.id],onClick:({key})=>onActionChange(key)}}><Button kind="quiet" disabled={disabled}>切换业务操作<DownOutlined aria-hidden="true"/></Button></CommandMenu>}
  </header>
  <div className="jj-material-workbench-body">
   <aside className="jj-material-workbench-index"><SectionHeading title="所需材料" level={3} appearance="group"/>
    <IndexSelection as="nav" label="选择所需材料" identity={actionId+':'+selected}>
     {[{title:'操作准备',kinds:['identity','execution','resource']},{title:'结果核对',kinds:['evidence','recovery']}].map(group=><div className="jj-material-workbench-group" key={group.title}><p>{group.title}</p>{materials.filter(item=>group.kinds.includes(item.kind)).map(item=>{const state=materialStatus(item.items);return <button type="button" className="jj-index-item jj-material-workbench-select" key={item.kind} aria-current={selected===item.kind?'true':undefined} onClick={()=>onSelect(item.kind)}><span aria-hidden="true">{icons[item.kind]}</span><span><strong>{materialNames[item.kind]}</strong><small>{item.kind==='identity'&&item.items.some(item=>item.reason_codes.includes('TEST_IDENTITY_LOGIN_REQUIRED'))?'会话需核对':state.label}</small></span></button>})}</div>)}
    </IndexSelection>
   </aside>
   <div className="jj-material-workbench-reading">{children}</div>
  </div>
  {footer}
 </section>
}
