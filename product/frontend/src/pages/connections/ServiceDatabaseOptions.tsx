import {useState} from 'react'
import {projectsApi,type DatabaseCapture} from '../../entities/application/api/projects'
import {Button} from '../../shared/ui/actions'
import {PasswordInput} from '../../shared/ui/PasswordInput'
import {Choice} from '../../shared/ui/Choice'
import {Dialog} from '../../shared/ui/Dialog'
import {Field,FormColumns,SectionHeading} from '../../shared/ui/layout'
import {ErrorNote} from '../../shared/ui/feedback'

const fresh=():DatabaseCapture=>({connection_id:'primary',engine:'POSTGRESQL',host:'127.0.0.1',port:5432,database:'',namespace:'public',username:'',password_env:'',table:'',resource_column:'id',owner_column:'',fields:[]})
export function ServiceDatabaseOptions({projectId,value,onChange,disabled}:{projectId?:string;value:DatabaseCapture[];onChange:(next:DatabaseCapture[])=>void;disabled:boolean}) {
    const [columns,setColumns]=useState('')
    const [draft,setDraft]=useState<DatabaseCapture>(),[index,setIndex]=useState(-1),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>()
    const open=(item:DatabaseCapture,position:number)=>{setDraft(item);setColumns(item.fields.join(', '));setIndex(position);setPassword('');setError(undefined)}
    const close=()=>{if(!busy){setDraft(undefined);setPassword('')}}
    const field=(label:string,key:'connection_id'|'database'|'namespace'|'username'|'table'|'resource_column'|'owner_column')=><Field label={label}><input disabled={busy} value={draft?.[key]??''} onChange={event=>setDraft(current=>current&&({...current,[key]:event.target.value,...(key==='database'&&current.engine==='MYSQL'?{namespace:event.target.value}:{})}))}/></Field>
    return <section className="jj-runtime-databases"><header><div><h4>PostgreSQL / MySQL 测试库</h4><p className="jj-small jj-muted">连接现有的本机隔离测试库；审计安装会在结果证明中单独审阅。</p></div><Button disabled={disabled||!projectId||value.length>=4} onClick={()=>open(fresh(),-1)}>添加连接</Button></header>
      {value.map((item,position)=><div className="jj-runtime-database" key={item.connection_id}><div className="jj-runtime-database-heading"><strong>{item.engine==='POSTGRESQL'?'PostgreSQL':'MySQL'} · {item.database} / {item.table}</strong><div className="jj-inline-actions"><Button kind="quiet" disabled={disabled} onClick={()=>open(item,position)}>编辑</Button><Button kind="quiet" disabled={disabled} onClick={()=>onChange(value.filter((_,i)=>i!==position))}>移除声明</Button></div></div><p className="jj-small jj-muted">{item.fields.join('、')} · {item.host}:{item.port}</p></div>)}
      {draft&&<Dialog title="声明测试数据库" size="wide" onClose={close} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={async()=>{
        setBusy(true);setError(undefined)
        try {
          if(!projectId)throw Error('当前应用尚未确认。')
          const projection=columns.split(',').map(name=>name.trim()).filter(Boolean)
          const names=[draft.connection_id,draft.database,draft.namespace,draft.username,draft.table,draft.resource_column,draft.owner_column,...projection]
          if(!Number.isInteger(draft.port)||draft.port<1024||draft.port>65535)throw Error('端口需在 1024 至 65535 之间。')
          if(projection.length>8||new Set(projection).size!==projection.length)throw Error('业务列最多 8 项且不能重复。')
          if(!projection.length||names.some(name=>! /^[A-Za-z_][A-Za-z0-9_]{0,62}$/.test(name)))throw Error('填写连接和业务记录字段，名称只接受字母、数字和下划线。')
          if(value.some((item,i)=>i!==index&&item.connection_id===draft.connection_id))throw Error('连接名称已经存在。')
          if(!password&&!draft.password_env)throw Error('首次配置需要数据库密码。')
          const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(projectId+'\0'+draft.connection_id))
          let name='JIEJIAN_DB_'+Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('').toUpperCase()
          if(password)name=(await projectsApi.databaseCredential(projectId,draft.connection_id,password)).password_env
          else if(name!==draft.password_env)throw Error('连接名称变化后需要重新提供密码。')
          const next={...draft,fields:projection,password_env:name}
          onChange(index<0?[...value,next]:value.map((item,i)=>i===index?next:item));setPassword('');setDraft(undefined)
        }catch(cause){setError(cause)}finally{setBusy(false)}
      }}>保存数据库设置</Button></>}>
        <FormColumns><section className="jj-field-stack"><SectionHeading title="连接位置" level={3}/><div className="jj-form-grid"><Field label="数据库类型"><Choice disabled={busy} value={draft.engine} onValueChange={engine=>setDraft({...draft,engine:engine as DatabaseCapture['engine'],port:engine==='MYSQL'?3306:5432,namespace:engine==='MYSQL'?draft.database:'public'})}><option value="POSTGRESQL">PostgreSQL 18</option><option value="MYSQL">MySQL 8.4 · InnoDB</option></Choice></Field>{field('连接名称','connection_id')}{field('数据库','database')}{draft.engine==='POSTGRESQL'&&field('Schema','namespace')}<Field label="本机端口"><input type="number" min={1024} max={65535} value={draft.port} disabled={busy} onChange={event=>setDraft({...draft,port:Number(event.target.value)})}/></Field>{field('数据库账号','username')}<Field label={draft.password_env?'更新密码（可选）':'数据库密码'}><PasswordInput autoComplete="new-password" value={password} disabled={busy} onChange={event=>setPassword(event.target.value)}/></Field></div></section>
        <section className="jj-field-stack"><SectionHeading title="用于判断结果的业务字段" level={3}/><div className="jj-field-stack">{field('普通数据表','table')}{field('唯一资源编号列','resource_column')}{field('资源所有者列','owner_column')}<Field label="需要核对的业务列"><input disabled={busy} value={columns} placeholder="例如 status, visibility" onChange={event=>setColumns(event.target.value)}/></Field></div><p className="jj-small jj-muted">最多 8 列，不包含密码、令牌等秘密。声明不会连接数据库或修改表。</p></section></FormColumns>
        {Boolean(error)&&<ErrorNote error={error}/>}
      </Dialog>}
    </section>
}
