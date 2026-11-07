import {useId,useState} from 'react'
import type {AsyncExportMapping} from '../api/proofSources'
import {Field} from '../../../shared/ui/layout'
import {Tabs} from '../../../shared/ui/Tabs'

export const emptyAsyncExport=():AsyncExportMapping=>({dispatch_task_path:[],status_path_template:'',file_path_template:'',task_path:[],state_path:[],resource_path:[],owner_path:[],subject_path:[],request_nonce_path:[],states:{},max_polls:16,poll_interval_us:100000,timeout_us:5000000,max_response_bytes:262144})
const paths=[['dispatch_task_path','提交响应中的任务编号','export.job_id'],['task_path','状态响应中的任务编号','job.id'],['state_path','任务状态','job.state'],['resource_path','资源编号','resource.id'],['owner_path','资源所有者','resource.owner_id'],['subject_path','实际执行主体','actor.id'],['request_nonce_path','原请求关联标记','request.nonce']] as const
const states=[['QUEUED','排队'],['RUNNING','运行中'],['SUCCESS','成功'],['FAILED','失败'],['CANCELLED','已取消'],['TIMED_OUT','超时']] as const
export function asyncExportReady(value:AsyncExportMapping) {
    return paths.every(([name])=>value[name].length>0&&value[name].length<=8&&value[name].every(part=>/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(part)))
      &&[value.status_path_template,value.file_path_template].every(path=>/^\/[A-Za-z0-9_./{}-]+$/.test(path)&&path.split('{task_id}').length===2&&!/[{}]/.test(path.replace('{task_id}',''))&&!path.split('/').some(part=>part==='.'||part==='..'))
      &&value.status_path_template!==value.file_path_template&&Number.isInteger(value.max_polls)&&value.max_polls>=1&&value.max_polls<=32&&value.timeout_us>=100000&&value.timeout_us<=5000000&&Object.keys(value.states).every(name=>/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name))&&Object.keys(value.states).length>=3&&Object.values(value.states).includes('SUCCESS')&&Object.values(value.states).some(state=>['FAILED','CANCELLED','TIMED_OUT'].includes(state))
}
export function AsyncExportFields({value,onChange,disabled=false}:{value:AsyncExportMapping;onChange:(value:AsyncExportMapping)=>void;disabled?:boolean}) {
    const [view,setView]=useState('task'),id=useId()
    // 保留正在输入的点号和分隔符，避免受控数组立即规范化后打断连续键入。
    const [pathText,setPathText]=useState(()=>Object.fromEntries(paths.map(([name])=>[name,value[name].join('.')])) as Record<(typeof paths)[number][0],string>)
    const [stateText,setStateText]=useState(()=>Object.fromEntries(states.map(([state])=>[state,Object.entries(value.states).filter(([,item])=>item===state).map(([name])=>name).join(', ')])) as Record<AsyncExportMapping['states'][string],string>)
    const changePath=(name:(typeof paths)[number][0],text:string)=>{setPathText({...pathText,[name]:text});onChange({...value,[name]:text.split('.').filter(Boolean)})}
    const changeState=(state:AsyncExportMapping['states'][string],text:string)=>{
        const names=text.split(',').map(name=>name.trim()).filter(Boolean),next=Object.fromEntries(Object.entries(value.states).filter(([,item])=>item!==state))
        names.forEach(name=>{next[name]=state})
        setStateText(Object.fromEntries(states.map(([item])=>[item,item===state?text:stateText[item].split(',').map(name=>name.trim()).filter(name=>name&&!names.includes(name)).join(', ')])) as typeof stateText)
        onChange({...value,states:next})
    }
    return <section className="jj-async-export-fields">
      <Tabs label="异步导出配置" value={view} idPrefix={id} panelId={id+'-panel'} onValueChange={setView} items={[{value:'task',label:'任务与文件'},{value:'states',label:'状态映射'},{value:'association',label:'关联字段'},{value:'budget',label:'等待限制'}]}/>
      <div role="tabpanel" id={id+'-panel'} aria-labelledby={id+'-'+view}>
      {view==='task'&&<><p className="jj-small jj-muted">任务编号取自实际提交响应；状态成功后，使用原操作账号接收完整文件。</p><div className="jj-form-grid">
        <Field label="任务查询路径"><input value={value.status_path_template} disabled={disabled} placeholder="/exports/{task_id}" onChange={event=>onChange({...value,status_path_template:event.target.value})}/></Field>
        <Field label="最终文件路径"><input value={value.file_path_template} disabled={disabled} placeholder="/exports/{task_id}/content" onChange={event=>onChange({...value,file_path_template:event.target.value})}/></Field>
        {paths.slice(0,3).map(([name,label,placeholder])=><Field key={name} label={label}><input value={pathText[name]} placeholder={placeholder} disabled={disabled} onChange={event=>changePath(name,event.target.value)}/></Field>)}
      </div></>}
      {view==='states'&&<><p className="jj-small jj-muted">按状态接口的真实取值映射；这里的成功只表示服务声明结束。</p><div className="jj-form-grid">{states.map(([state,label])=><Field key={state} label={label+'的原始状态值'+(['RUNNING','CANCELLED','TIMED_OUT'].includes(state)?'（可选）':'')}><input value={stateText[state]} disabled={disabled} placeholder="按接口真实取值填写，多个值用逗号分隔" onChange={event=>changeState(state,event.target.value)}/></Field>)}
      </div></>}
      {view==='association'&&<><p className="jj-small jj-muted">这些字段必须来自状态响应，并与已核验的账号、资源和原请求一致。无法对应时保留缺口。</p><div className="jj-form-grid">{paths.slice(3).map(([name,label,placeholder])=><Field key={name} label={label}><input value={pathText[name]} placeholder={placeholder} disabled={disabled} onChange={event=>changePath(name,event.target.value)}/></Field>)}</div></>}
      {view==='budget'&&<><div className="jj-form-grid"><Field label="最多查询次数"><input type="number" min={1} max={32} disabled={disabled} value={value.max_polls} onChange={event=>onChange({...value,max_polls:Number(event.target.value)})}/></Field><Field label="总等待时间（秒）"><input type="number" min={.1} max={5} step={.1} disabled={disabled} value={value.timeout_us/1000000} onChange={event=>onChange({...value,timeout_us:Number(event.target.value)*1000000})}/></Field></div><p className="jj-small jj-muted">采用有限退避并共享本次检查预算。取消后停止采集，后台工作仍需核对；提交请求不会自动重发。</p></>}
      </div>
    </section>
}
