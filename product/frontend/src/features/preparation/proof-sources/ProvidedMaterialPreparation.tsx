// 官方示例把固定虚构材料集中说明并一次确认；普通应用仍按实际账号与资源整理。
import { Alert, Button, Modal } from 'antd'
import { usePreparationBatch } from './usePreparationBatch'
import type { PreparationView } from '../../../api/preparation/preparation'
import { materialStatus } from '../materials/materialStatus'

export function ProvidedMaterialPreparation({projectId,onChanged,open,onOpenChange,prepared=false,onContinue,currentPreparation,outdated=false}:{
  projectId:string;onChanged:()=>Promise<unknown>;open:boolean;onOpenChange:(value:boolean)=>void;prepared?:boolean;onContinue?:()=>void;currentPreparation?:PreparationView;outdated?:boolean
}) {
  const batch=usePreparationBatch(projectId,onChanged)
  const {busy,error}=batch, message=batch.value?.message
  const actions=currentPreparation?.actions ?? []
  // 批次的 READY 只描述当时执行结果；源码改变后，以同一份当前准备投影更新五类汇总。
  const currentGroups=[
    {label:'真实账号',items:actions.flatMap(action=>action.identity_requirements.slots)},
    {label:'动作录制',items:actions.map(action=>action.execution)},
    {label:'测试资源',items:actions.flatMap(action=>action.resources)},
    {label:'结果证明',items:actions.flatMap(action=>action.effect_evidence)},
    {label:'恢复方式',items:actions.map(action=>action.recovery)},
  ]
  const start=async()=>{
    onOpenChange(false);await batch.start('OFFICIAL')
  }
  return <section className="provided-material-preparation" aria-label="自动准备示例材料">
    <div><h3>{prepared?'示例材料已准备好':'一键准备示例材料'}</h3><p>{prepared?'账号、操作步骤、测试资源和文件都已准备好，可以继续检查当前权限要求。':'准备负责人和评审账号、操作步骤、展馆测试数据，以及用来核对下载内容的 ZIP 和 PDF。'}</p>
      {message&&batch.value?.state!=='SUCCEEDED'&&<p role="status">{message}</p>}
      {!busy && <ul className="provided-material-progress" aria-label="当前材料准备状态">{currentGroups.map(group=><li key={group.label}><span>{group.label}</span><strong>{outdated || !currentPreparation ? '等待同步' : materialStatus(group.items)}</strong></li>)}</ul>}
      {busy&&batch.value?.identities?.length ? <ul className="provided-material-progress" aria-label="账号准备进度">{batch.value.identities.map(item=><li key={item.account}><span>{item.account==='curator'?'项目负责人账号':'评审账号'}</span><strong>{item.state==='PREPARED'?'已就绪':item.state==='CANCELLED'?'已停止':item.state==='FAILED'?'需要处理':'正在登录'}</strong></li>)}</ul>:null}
      {busy&&batch.value?.items?.length ? <ul className="provided-material-progress" aria-label="证明核对进度">{batch.value.items.map(item=><li key={item.label}><span>{item.label}</span><strong>{({READY:'已就绪',CHECKING:'正在核对',BLOCKED:'需要处理',WAITING:'等待核对'} as Record<string,string>)[item.state]??'等待同步'}</strong></li>)}</ul>:null}
    </div>
    {batch.queryRequired?<Button type="primary" loading={batch.sending} onClick={()=>void batch.refresh()}>查询本次准备</Button>:busy&&batch.value?<Button danger loading={batch.value.cancel_requested} onClick={()=>void batch.cancel()}>停止材料准备</Button>:<Button type="primary" loading={batch.sending} onClick={()=>prepared&&onContinue?onContinue():onOpenChange(true)}>{prepared&&onContinue?'前往检查':error?'继续准备示例材料':'一键准备示例材料'}</Button>}
    {batch.retrying&&!batch.queryRequired&&<Button onClick={()=>void batch.refresh()}>查询本次准备</Button>}
    {error&&<Alert type="warning" showIcon message={error}/>}
    <Modal open={open} title="准备这份官方示例的检查材料" okText="确认并一键准备" cancelText="暂不准备" onCancel={()=>onOpenChange(false)} onOk={()=>void start()}>
      <p>这次只处理当前数字展馆示例中的虚构数据：</p>
      <ul><li>登录项目负责人 curator 和评审 judge，准备两种身份的检查。</li><li>使用校园展馆 campus，准备下载、预览和恢复操作。</li><li>使用示例提供的内部 ZIP 和公开 PDF，作为下载内容的对照文件。</li><li>允许读取这份展馆的身份与业务记录，自动核对这些材料，并把通过核对的材料用于本示例检查。</li></ul>
      <p>完成后会显示哪些材料已准备好；正式权限检查需要你再点击开始。离开页面后准备仍会继续，再次打开可以查看同一批次的进度。</p>
    </Modal>
  </section>
}
