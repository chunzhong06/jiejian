import {useState} from 'react'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import {Tabs} from '../../../shared/ui/Tabs'
import {Field} from '../../../shared/ui/layout'
import {Choice} from '../../../shared/ui/Choice'
import {Button} from '../../../shared/ui/actions'
import {newParameter,sensitiveParameter,type EditableStep,type FlowParameter,type InputLocation,type InputSource} from './flowInputs'

const locations:Record<InputLocation,string>={QUERY:'查询参数',HEADER:'请求头',JSON_BODY:'JSON 正文',PATH:'路径取值'}
const sources:Record<InputSource,string>={LITERAL:'固定非敏感值',CASE_RESOURCE_ID:'本次测试的资源编号',CASE_SUBJECT_ID:'界鉴测试账号编号',PRIOR_STEP_JSON_PATH:'前序响应的 JSON 字段',PRIOR_STEP_HEADER:'前序响应头',PRIOR_STEP_COOKIE:'前序响应 Cookie',PRIOR_STEP_LOCATION:'前序响应的跳转地址'}

export function FlowRequestInputs({step,previous,busy,onChange}:{step:EditableStep;previous:EditableStep[];busy:boolean;onChange:(value:EditableStep)=>void}){
  const [location,setLocation]=useState<InputLocation>(()=>step.parameters[0]?.location??(step.path.includes('{case_resource_id}')?'PATH':'QUERY'))
  const implicitResource=step.path.includes('{case_resource_id}')&&!step.parameters.some(item=>item.location==='PATH'&&item.name==='case_resource_id')
  const rows=step.parameters.map((value,index)=>({value,index})).filter(item=>item.value.location===location)
  const change=(index:number,value:FlowParameter)=>onChange({...step,parameters:step.parameters.map((item,i)=>i===index?value:item)})
  const chooseSource=(item:FlowParameter,source:InputSource)=>({...item,source,json:false,
    producer:item.producer||previous.at(-1)?.id||'',path:source==='PRIOR_STEP_LOCATION'?'$location':source==='PRIOR_STEP_HEADER'?'X-Request-Token':source==='PRIOR_STEP_COOKIE'?'csrf':source==='PRIOR_STEP_JSON_PATH'?'$.id':item.path,
    secret:source.startsWith('PRIOR_STEP_')&&source!=='PRIOR_STEP_LOCATION'&&location!=='PATH'&&(item.secret||sensitiveParameter(item.name))})
  return <section className="jj-flow-inputs" aria-label="请求输入">
    <header><Tabs density="compact" divider={false} label="输入位置" value={location} panelId={'flow-input-panel-'+step.id} idPrefix={'flow-input-'+step.id} className="jj-flow-input-tabs"
      items={Object.entries(locations).map(([value,label])=>({value,label:label+' '+(step.parameters.filter(item=>item.location===value).length+(value==='PATH'&&implicitResource?1:0))}))} onValueChange={value=>setLocation(value as InputLocation)}/><Button kind="quiet" icon={<PlusOutlined aria-hidden="true"/>} disabled={busy} onClick={()=>onChange({...step,parameters:[...step.parameters,newParameter(location)]})}>添加{locations[location]}</Button></header>
    <div role="tabpanel" id={'flow-input-panel-'+step.id} aria-labelledby={'flow-input-'+step.id+'-'+location}>
      {location==='PATH'&&implicitResource&&<dl className="jj-flow-input-builtin"><dt>case_resource_id</dt><dd>本次测试的资源编号<span>由接口路径中的占位生成，随路径调整。</span></dd></dl>}
      {!rows.length&&!(location==='PATH'&&implicitResource)&&<p className="jj-small jj-muted jj-flow-input-empty">{location==='PATH'?'暂无路径取值。可在接口路径加入占位，再在这里指定来源。':`此请求尚无${locations[location]}；不需要时可直接继续。`}</p>}
      {rows.map(({value:item,index})=>{
        const prior=item.source.startsWith('PRIOR_STEP_')
        return <div className="jj-flow-input-row" key={item.slotId+':'+index} role="group" aria-label={locations[location]+'：'+(item.name||'新参数')}>
          <Field label={location==='PATH'?'路径占位名称':'参数名称'}><input value={item.name} disabled={busy} onChange={event=>{
            const next={...item,name:event.target.value}
            change(index,sensitiveParameter(next.name)&&next.source==='LITERAL'?{...chooseSource(next,'PRIOR_STEP_JSON_PATH'),value:''}:next)
          }}/></Field>
          <Field label="数据来源"><Choice disabled={busy} value={item.source} onValueChange={value=>change(index,chooseSource(item,value as InputSource))}>
            {Object.entries(sources).map(([value,label])=><option key={value} value={value} disabled={value==='LITERAL'&&sensitiveParameter(item.name)||value==='CASE_RESOURCE_ID'&&location==='HEADER'}>{label}</option>)}
          </Choice></Field>
          <Button kind="quiet" className="jj-flow-input-remove" disabled={busy} icon={<DeleteOutlined aria-hidden="true"/>} aria-label={'移除参数：'+(item.name||'新参数')} onClick={()=>onChange({...step,parameters:step.parameters.filter((_,i)=>i!==index)})}/>
          {item.source==='LITERAL'&&<div className="jj-flow-input-value"><Field label="发送的值"><input disabled={busy} value={item.value} onChange={event=>change(index,{...item,value:event.target.value})}/></Field></div>}
          {prior&&<><Field label="前序请求"><Choice disabled={busy} value={item.producer} onValueChange={producer=>change(index,{...item,producer})}><option value="" disabled>选择此前的请求</option>{previous.map((candidate,i)=><option key={candidate.id} value={candidate.id}>第 {i+1} 步 · {candidate.method} {candidate.path}</option>)}</Choice></Field>
            {item.source!=='PRIOR_STEP_LOCATION'&&<Field label={item.source==='PRIOR_STEP_JSON_PATH'?'JSON 字段位置':item.source==='PRIOR_STEP_HEADER'?'响应头名称':'Cookie 名称'}><input disabled={busy} value={item.path} onChange={event=>change(index,{...item,path:event.target.value})}/></Field>}</>}
          {item.source==='CASE_RESOURCE_ID'&&<p className="jj-flow-input-value jj-small jj-muted">执行时使用本次测试数据编号；正式检查按规则选择对应资源。</p>}
          {item.source==='CASE_SUBJECT_ID'&&<p className="jj-flow-input-value jj-small jj-muted">传入界鉴测试账号的引用编号，不代替应用中的真实主体核验。</p>}
          {prior&&<div className="jj-flow-input-type"><Field label="值的类型"><Choice disabled={busy} value={item.slot?.value_type as string??'STRING'} onValueChange={value=>change(index,{...item,slot:{...item.slot,value_type:value}})}>{['STRING','INTEGER','BOOLEAN','JSON'].map(value=><option key={value} value={value}>{({STRING:'文本',INTEGER:'整数',BOOLEAN:'布尔值',JSON:'JSON'})[value as 'STRING']}</option>)}</Choice></Field></div>}
          {prior&&location!=='PATH'&&item.source!=='PRIOR_STEP_LOCATION'&&<label className="jj-checkbox"><input type="checkbox" disabled={busy||sensitiveParameter(item.name)&&item.secret} checked={item.secret} onChange={event=>change(index,{...item,secret:event.target.checked})}/><span>敏感值，仅在本次执行内存中传递</span></label>}
          {location==='JSON_BODY'&&item.source==='LITERAL'&&<label className="jj-checkbox jj-flow-input-value"><input type="checkbox" disabled={busy} checked={item.json} onChange={event=>change(index,{...item,json:event.target.checked})}/><span>按数字、布尔值或 JSON 读取</span></label>}
        </div>
      })}
      {location==='JSON_BODY'&&!rows.length&&<label className="jj-checkbox"><input type="checkbox" disabled={busy} checked={step.bodyKind==='JSON'} onChange={event=>onChange({...step,bodyKind:event.target.checked?'JSON':'EMPTY'})}/><span>发送空 JSON 对象</span></label>}
    </div>
  </section>
}
