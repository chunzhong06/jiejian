// 同源接入明确区分恢复旧事实与建立空项目；本地选择本身不执行恢复或清除。
import {useState} from 'react'
import {Button,Input,Radio,Select} from 'antd'
import type {ConnectionChoice,ConnectionPreview} from '../../api/applications/projects'

export function ApplicationReentry({preview,busy,uncertain,onChoose,onRead,onCancel}:{preview:ConnectionPreview;busy:boolean;uncertain:boolean;onChoose:(choice:ConnectionChoice,name?:string)=>void;onRead:()=>void;onCancel:()=>void}) {
  const [mode,setMode]=useState<'RESUME'|'NEW'>()
  const [projectId,setProjectId]=useState(preview.projects.length===1?preview.projects[0].project_id:undefined)
  const [name,setName]=useState(`${preview.projects[0]?.name??'应用'} · 新接入`.slice(0,128))
  return <section className="application-step application-reentry"><h2>{preview.projects.length?'这个目录以前接入过':'本次接入结果待确认'}</h2><p className="editorial-muted">{uncertain?'请先查询本次操作的实际结果，不重复创建或恢复项目。':'请选择继续原项目，还是从空白开始。移除应用会保留权限与历史，不等于清空。'}</p><p className="application-reentry-path">{preview.source_root}</p>
    {!uncertain&&<>
    <Radio.Group className="product-choice-cards" aria-label="再次接入方式" value={mode} disabled={busy||uncertain} onChange={e=>setMode(e.target.value)}><Radio value="RESUME"><strong>恢复或继续原项目</strong><span>继续使用原权限、候选和源码授权，历史记录仍在；测试账号凭据可能需要重新准备。</span></Radio><Radio value="NEW"><strong>作为全新项目接入</strong><span>重新授权分析、整理和批准权限。原项目单独保留，不复制原权限或材料。</span></Radio></Radio.Group>
    {mode==='RESUME'&&<label className="application-reentry-field"><span>选择原项目</span><Select aria-label="选择恢复的原项目" value={projectId} disabled={busy||uncertain} onChange={setProjectId} options={preview.projects.map(item=>({value:item.project_id,label:`${item.name??item.project_id} · ${item.status==='ARCHIVED'?'已移除':'活动项目'}`}))}/></label>}
    {mode==='NEW'&&<label className="application-reentry-field"><span>新项目名称</span><Input value={name} maxLength={128} disabled={busy||uncertain} onChange={e=>setName(e.target.value)}/></label>}
    </>}
    <div className="application-reentry-actions"><Button disabled={busy||uncertain} onClick={onCancel}>重新选择目录</Button>{uncertain?<Button type="primary" loading={busy} onClick={onRead}>查询本次接入结果</Button>:<Button type="primary" disabled={busy||!mode||mode==='RESUME'&&!projectId||mode==='NEW'&&!name.trim()} loading={busy} onClick={()=>mode&&onChoose({mode,existing_project_id:mode==='RESUME'?projectId:undefined,expected_snapshot:preview.snapshot,operation_id:mode==='NEW'?crypto.randomUUID().replaceAll('-',''):undefined},mode==='NEW'?name.trim():undefined)}>{mode==='NEW'?'建立全新项目':mode==='RESUME'?'继续所选原项目':'先选择接入方式'}</Button>}</div>
  </section>
}
