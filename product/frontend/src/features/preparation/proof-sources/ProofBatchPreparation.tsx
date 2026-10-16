// 人集中核对 Agent 提交的实际候选后续接准备；确认期间的任何配置变化都重新审阅。
import { Alert, Button, Checkbox, Modal } from 'antd'
import { useState } from 'react'
import type { ProofContext } from '../../../api/preparation/proofSources'
import { proofSourcesApi } from '../../../api/preparation/proofSources'
import { usePreparationBatch } from './usePreparationBatch'

export function ProofBatchPreparation({context,onChanged}:{context:ProofContext;onChanged:()=>Promise<unknown>}) {
  const [review,setReview]=useState<ProofContext>(),[confirmed,setConfirmed]=useState(false)
  const batch=usePreparationBatch(context.project_id,onChanged)
  const {busy,error}=batch, message=batch.value?.message
  const ready=context.sources.length>0&&context.runtime_available&&context.sources.every(item=>context.resources.some(resource=>resource.resource_binding_id===item.config.resource_binding_id)&&item.config.source_kind!=='JSON_HTTP_RESOURCE'&&(item.config.source_kind!=='REFERENCE_FILE'||item.config.reference_artifact))
  const start=async()=>{
    if(!review||!confirmed||busy)return
    setReview(undefined);await batch.start('REVIEWED',review)
  }
  return <section className="provided-material-preparation" aria-label="集中核对材料">
    <div><h3>确认用途后，逐项准备检查材料</h3><p>{ready?'确认账号、资源和读取位置后，界鉴会逐项检查，并将通过核对的材料用于这次检查。':'先补齐文件、资源对应和运行条件，再集中核对这批材料。'}</p>{message&&<p role="status">{message}</p>}</div>
    {batch.queryRequired?<Button type="primary" loading={batch.sending} onClick={()=>void batch.refresh()}>查询本次准备</Button>:busy&&batch.value?<Button danger loading={batch.value.cancel_requested} onClick={()=>void batch.cancel()}>停止材料准备</Button>:<Button type="primary" loading={batch.sending} disabled={!ready} onClick={()=>{setConfirmed(false);setReview(context)}}>核对这批材料</Button>}
    {batch.retrying&&!batch.queryRequired&&<Button onClick={()=>void batch.refresh()}>查询本次准备</Button>}
    {error&&<Alert type="warning" showIcon message={error}/>}
    <Modal open={Boolean(review)} title="确认这批检查材料" okText="允许读取并准备这批材料" cancelText="返回修改" okButtonProps={{disabled:!confirmed}} onCancel={()=>setReview(undefined)} onOk={()=>void start()} width={760}>
      {review&&<><p>应用地址：{review.runtime_origin}</p>{review.sources.map(source=>{
        const action=review.actions.find(item=>item.action_id===source.config.action_id),resource=review.resources.find(item=>item.resource_binding_id===source.config.resource_binding_id)
        return <section key={source.source_id} className="proof-batch-item"><h3>{action?.effects.find(item=>item.effect_id===source.config.effect_id)?.label??action?.label}</h3>
          <p>测试资源：{resource?.resource_id??'尚未确认'}。读取账号：{source.config.identity_claims.map(claim=>review.identities.find(item=>item.identity_id===claim.identity_id)?.label??claim.application_subject_id).join('、')}。</p>
          <p>读取位置：{source.config.source_kind==='CREATED_OBJECT_RECORDS'?`整个集合 /collections/${source.config.collection}（最多 256 个对象的标识、归属、版本、内容摘要及本次创建记录）`:source.config.relative_path_template}；{[...new Set(source.config.identity_claims.map(item=>item.request_path))].join('、')}。</p>
          <p>每次最多 {Math.ceil(source.config.max_response_bytes/1024)} KiB，超时 {source.config.timeout_us/1_000_000} 秒。</p>
          {source.config.reference_artifact&&<Button href={proofSourcesApi.referenceDownload(review.project_id,source.config.reference_artifact.asset_id)}>查看这项测试文件</Button>}
        </section>
      })}<p>确认后，界鉴会读取所列材料，核对账号和资源，并把通过核对的材料用于后续检查。缺失或变化的项目会停下，已有结果保留。</p>
      <Checkbox checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}>我已核对这些账号、资源和文件，允许上述读取及材料采用</Checkbox></>}
    </Modal>
  </section>
}
