import {useState} from 'react'
import type {EvidenceRecordView} from '../../../entities/check/api/currentChecks'
import {text} from '../../../shared/lib/format'
import {ObjectHeading} from '../../../shared/ui/layout'
import {Badge} from '../../../shared/ui/feedback'

export function EvidenceRecord({value}:{value:EvidenceRecordView}) {
  // 原文首次展开才构建；关闭后保留节点，继续使用公共收起动效。
  const [originalOpened,setOriginalOpened]=useState(false)
  const context=value.verification.filter(item=>['rule','experiment'].includes(item.key))
  const collection=value.verification.filter(item=>['method','association'].includes(item.key))
  const reason=value.verification.find(item=>item.key==='reason')
  return <article className="jj-record-reading" data-has-values={value.values.length>0} aria-label="封存记录详情">
    <header className="jj-object-line"><h3>{text(value.record.label)}</h3><Badge tone={value.role==='PROOF'?'accent':'neutral'}>{value.role==='PROOF'?'业务证明':'辅助记录'}</Badge></header>
    <div className="jj-record-findings"><section className="jj-record-conclusion" aria-label="记录核对结果"><ObjectHeading level={4} caption="记录核对结果" title={text(value.summary)}/></section>
    <section className="jj-record-meaning" aria-label="所属检查的判断"><ObjectHeading level={4} caption="这项检查的判断" title={text(value.published_judgement)} description={reason&&<p>{text(reason.text)}</p>}/></section></div>
    <div className="jj-record-supplement">
    {value.values.length>0&&<details className="jj-record-disclosure"><summary>查看核对数据</summary><dl className="jj-facts jj-record-values" data-layout="columns" aria-label="记录中的值">{value.values.map((item,index)=><div key={index}>
      <dt>{text(item.label)}</dt><dd>{item.value!==undefined?displayValue(item.value):<span className="jj-record-comparison"><span><small>{item.before_label??'操作前'}</small>{displayValue(item.before)}</span><span><small>{item.after_label??'操作后'}</small>{displayValue(item.after)}</span></span>}</dd>
    </div>)}</dl></details>}
    {collection.length>0&&<details className="jj-record-disclosure"><summary>核对依据与采集范围</summary><div className="jj-record-context">{collection.map(item=><section key={item.key}><h4>{item.key==='method'?'采集方式':'记录关联'}</h4><p>{text(item.text)}</p></section>)}</div></details>}
    {context.length>0&&<details className="jj-record-disclosure"><summary>检查背景与已发布判断</summary><div className="jj-record-background">{context.map(item=><section key={item.key}><div className="jj-object-line"><h4>{text(item.title)}</h4>{item.status==='UNKNOWN'&&<Badge tone="caution">尚未确认</Badge>}</div><p>{text(item.text)}</p></section>)}</div></details>}
    <details className="jj-record-disclosure" onToggle={event=>{if(event.currentTarget.open)setOriginalOpened(true)}}><summary>适用范围与封存原文</summary><div className="jj-record-original">
      {value.limitations.length>0&&<section><h4>适用范围</h4><ul>{value.limitations.map((item,index)=><li key={index}>{text(item)}</li>)}</ul></section>}
      {originalOpened&&<section><h4>原始片段与技术位置</h4><pre>{JSON.stringify({location:value.location,fragment:value.fragment},null,2)}</pre></section>}
    </div></details></div>
  </article>
}

function displayValue(value:unknown):string {
  return value===null||value===undefined?'未记录':typeof value==='boolean'?value?'是':'否':typeof value==='object'?JSON.stringify(value):String(value)
}
