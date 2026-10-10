// 闲置运行文件的扫描、固定计划选择和只读回执恢复；未知写结果不会触发第二次删除。
import {useEffect,useRef,useState} from 'react'
import {Alert,Button,Checkbox,Modal,Spin} from 'antd'
import {systemApi,type MaintenanceStatus,type MaintenanceOperationResult} from '../../api/system/system'
import {ApiError} from '../../api/http'
import './maintenance.css'

const names:Record<string,string>={builds:'旧前端构建',build_cache:'下载与构建缓存',components:'闲置运行组件',assistant:'AI 辅助缓存',logs:'历史日志',temporary:'运行临时文件'}
const pendingKey='jiejian.maintenance.pending'
const size=(value:number|null|undefined)=>value==null?'未确认':value<1024?`${value} B`:value<1024**2?`${(value/1024).toFixed(1)} KiB`:`${(value/1024**2).toFixed(1)} MiB`

export function MaintenancePanel(){
  const [status,setStatus]=useState<MaintenanceStatus|null>(null)
  const [reading,setReading]=useState(true),[busy,setBusy]=useState(false),[failed,setFailed]=useState(false)
  const [error,setError]=useState(''),[preview,setPreview]=useState<MaintenanceOperationResult|null>(null)
  const [selected,setSelected]=useState<string[]>([]),[result,setResult]=useState<MaintenanceOperationResult|null>(null)
  const [pending,setPending]=useState<string|null>(null)
  const [previewOpen,setPreviewOpen]=useState(false)
  const previewEpoch=useRef(0)
  const alive=useRef(true),epoch=useRef(0),writing=useRef(false)
  const scan=async()=>{
    const version=++epoch.current;setReading(true)
    try{
      const next=await systemApi.maintenanceStatus()
      if(!alive.current||version!==epoch.current)return
      setStatus(next);setFailed(false);setError('')
      try{const stored=JSON.parse(sessionStorage.getItem(pendingKey)||'null');if(stored?.root===next.protected.data)setPending(stored.planId)}catch{/* 读取偏好失败不影响扫描。 */}
    }catch(e){if(alive.current&&version===epoch.current){setFailed(true);setError((e as Error).message)}}
    finally{if(alive.current&&version===epoch.current)setReading(false)}
  }
  useEffect(()=>{alive.current=true;void scan();return()=>{alive.current=false;epoch.current++}},[])
  const accept=(next:MaintenanceOperationResult)=>{
    setResult(next);setStatus(next.status);setPreview(null);setPreviewOpen(false);setPending(null);setError('')
    try{sessionStorage.removeItem(pendingKey)}catch{/* 已回读结果，残留定位只会再次查询。 */}
  }
  const showPreview=async()=>{
    const version=++previewEpoch.current
    setPreview(null);setSelected([]);setPreviewOpen(true);setBusy(true);setError('')
    try{const next=await systemApi.maintenanceOperation('clear-all',{confirmed:false,dry_run:true});if(alive.current&&version===previewEpoch.current){setPreview(next);setSelected(next.targets.map(item=>item.item_id))}}
    catch(e){if(alive.current&&version===previewEpoch.current){setError((e as Error).message);setPreviewOpen(false)}}finally{if(alive.current&&version===previewEpoch.current)setBusy(false)}
  }
  const execute=async()=>{
    if(!preview||!selected.length||writing.current||pending)return
    writing.current=true;setBusy(true)
    const planId=preview.plan_id
    try{
      // 在写请求发出前保存非秘密计划定位，刷新页面后仍能查询同一份回执。
      try{sessionStorage.setItem(pendingKey,JSON.stringify({root:status?.protected.data,planId}))}
      catch{setError('浏览器无法保存清理回执定位，请允许本页会话存储后重试。');return}
      setPending(planId)
      const next=await systemApi.maintenanceOperation('clear-all',{confirmed:true,dry_run:false,plan_id:planId,item_ids:selected})
      if(alive.current)accept(next)
    }catch(e){if(alive.current){setPreview(null);setPreviewOpen(false)
      if(e instanceof ApiError&&(e.code==='INPUT_INVALID'||e.executionStarted===false)){
        setPending(null);try{sessionStorage.removeItem(pendingKey)}catch{/* 服务端明确未执行，当前会话可重新扫描。 */}
        setError(e.message)
      }else setError('清理请求已发出，执行结果暂未确认。请读取这次结果。')
    }}
    finally{writing.current=false;if(alive.current)setBusy(false)}
  }
  const recover=async()=>{
    if(!pending)return
    setBusy(true)
    try{const next=await systemApi.maintenanceOutcome(pending);if(!alive.current)return
      if(next.state==='COMPLETED'&&next.result)accept(next.result)
      else setError('尚未取得这次清理的完成回执。当前保留计划定位，请稍后再次读取结果。')
    }catch(e){if(alive.current)setError((e as Error).message)}finally{if(alive.current)setBusy(false)}
  }
  const inventory=status?.inventory,cleanable=inventory?.filter(item=>item.state==='CLEANABLE')??[]
  const groups=Object.keys(names).map(category=>({category,items:cleanable.filter(item=>item.category===category)})).filter(group=>group.items.length)
  return <section className="runtime-maintenance" aria-label="清理闲置运行文件">
    <div className="maintenance-heading"><div><h2>清理闲置运行文件</h2><p>仅管理启动和运行模块登记的文件。保留应用、权限、检查历史和准备材料。</p></div><Button onClick={()=>void scan()} loading={reading} disabled={busy}>重新扫描</Button></div>
    {reading&&!status&&<Spin aria-label="正在扫描运行文件"/>}
    {error&&<Alert className="flow-feedback" type={pending?'warning':'error'} showIcon message={failed?'扫描暂时失败':pending?'清理结果待确认':'操作未完成'} description={error}/>}
    {status&&!inventory&&<Alert type="info" message="重新启动界鉴后可使用新版清理功能"/>}
    {failed&&status&&<p className="editorial-muted">当前显示上次扫描结果，扫描成功后才能清理。</p>}
    {pending&&<Button onClick={()=>void recover()} loading={busy}>读取本次清理结果</Button>}
    {inventory&&<>
      <h3>可清理</h3>
      {groups.length?<div className="maintenance-categories">{groups.map(group=><div key={group.category}><span>{names[group.category]}</span><span>{group.items.length} 项</span><strong>{size(group.items.reduce((sum,item)=>sum+(item.bytes??0),0))}</strong></div>)}</div>:<p className="editorial-muted">暂未发现可以确认清理的闲置文件。</p>}
      <p className="editorial-muted">显示的是文件大小；硬链接等情况可能使实际释放空间不同。</p>
      <details><summary>当前需要保留</summary><p>当前前端、运行依赖、GUI 配置、全部业务资料，以及活动任务和恢复过程使用的内容。</p>{inventory.filter(item=>item.state==='PROTECTED').map(item=><div className="maintenance-file" key={item.relative_path}><span>{item.label} · {item.relative_path}</span><small>{item.reason}</small></div>)}</details>
      {!!inventory.some(item=>item.state==='UNKNOWN')&&<details><summary>暂无法确认 · {inventory.filter(item=>item.state==='UNKNOWN').length} 项</summary>{inventory.filter(item=>item.state==='UNKNOWN').map(item=><div className="maintenance-file" key={item.relative_path}><span>{item.relative_path}</span><small>{item.reason}</small></div>)}</details>}
      <div className="maintenance-actions"><Button type="primary" disabled={!cleanable.length||failed||reading||!!pending} loading={busy&&!pending} onClick={()=>void showPreview()}>预览清理</Button></div>
    </>}
    {result&&<Alert className="flow-feedback" type={result.counts.FAILED?'warning':'success'} showIcon message="本次清理已完成" description={`已清理 ${result.counts.DELETED} 项，跳过 ${result.counts.ALREADY_MISSING+result.counts.SKIPPED_IN_USE+result.counts.SKIPPED_CHANGED} 项，失败 ${result.counts.FAILED} 项。`}/>}
    {!!result?.results.length&&<details><summary>查看本次处理明细</summary>{result.results.map(item=><div className="maintenance-file" key={item.item_id}><span>{item.relative_path}</span><small>{item.reason}</small></div>)}</details>}
    <Modal open={previewOpen} title="确认清理范围" okText="清理所选" cancelText="取消" confirmLoading={busy&&!!preview} okButtonProps={{disabled:busy||!preview||!selected.length||!!pending}} cancelButtonProps={{disabled:!!pending}} closable={!pending} maskClosable={!pending} onCancel={()=>{if(!pending){previewEpoch.current++;setPreviewOpen(false);setPreview(null);setBusy(false)}}} onOk={()=>void execute()}>
      {!preview?<div role="status"><Spin size="small"/> 正在核对可清理的文件…</div>:<>
      <p>已选 {selected.length} 项，文件大小 {size(preview?.targets.filter(item=>selected.includes(item.item_id)).reduce((sum,item)=>sum+item.estimated_bytes,0))}。</p>
      <p className="editorial-muted">确认时只处理这份计划；重新被使用或发生变化的项目会跳过。</p>
      <div className="maintenance-selection">{preview?.targets.map(item=><Checkbox key={item.item_id} checked={selected.includes(item.item_id)} disabled={busy} onChange={event=>setSelected(items=>event.target.checked?[...items,item.item_id]:items.filter(id=>id!==item.item_id))}><span>{item.label} · {size(item.estimated_bytes)}</span><small>{item.relative_path}</small></Checkbox>)}</div>
      </>}
    </Modal>
  </section>
}
