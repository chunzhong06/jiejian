import {useState} from 'react'
import {Choice} from '../../shared/ui/Choice'
import type {RuntimeCapabilities,RuntimeSettings,SqliteCapture} from '../../entities/application/api/projects'
import {Button} from '../../shared/ui/actions'
import {Badge} from '../../shared/ui/feedback'
import {Field,FormColumns,SectionHeading,ObjectIdentity} from '../../shared/ui/layout'
import {ServiceDatabaseOptions} from './ServiceDatabaseOptions'

export function RuntimeOptions({projectId,capabilities,value,onChange,disabled}:{projectId?:string;capabilities?:RuntimeCapabilities;value:RuntimeSettings;onChange:(next:RuntimeSettings)=>void;disabled:boolean}) {
    const databases=value.sqlite??[]
    const suggestions=capabilities?.sqlite_setup
    const availablePaths=suggestions?.paths.filter(path=>!databases.some(database=>database.relative_path===path))??[]
    const [manual,setManual]=useState<number>()
    const update=(index:number,next:SqliteCapture)=>onChange({...value,sqlite:databases.map((item,i)=>i===index?next:item)})
    const add=(path='')=>{
        const table=suggestions?.paths.length===1&&suggestions.tables.length===1?suggestions.tables[0]:undefined
        onChange({...value,sqlite:[...databases,{relative_path:path,tables:[{table:table?.name??'',resource_column:table?.primary_key??'',owner_column:'',fields:[]}]}]})
    }
    return <details className="jj-runtime-options">
        <summary>依赖与测试数据 <span>{databases.length?databases.length+' 个数据库':'选择用于检查的测试数据'}</span></summary>
        <div className="jj-runtime-options-body">
            <div className="jj-runtime-dependencies"><div><ObjectIdentity name={<strong>{capabilities?.package??'Node 应用'}</strong>} status={<Badge tone={capabilities?.dependencies==='LOCKED'?'positive':'neutral'}>{capabilities?.dependencies==='LOCKED'?'npm 依赖已锁定':capabilities?.dependencies==='NEEDS_CONFIGURATION'?'需要 npm 锁文件':'无需 npm 安装'}</Badge>}/></div>
                {Boolean(capabilities?.build_scripts.length)&&<Field label="构建步骤"><Choice value={value.build_script??''} disabled={disabled} onValueChange={script=>onChange({...value,build_script:script||null})}><option value="">直接运行 JavaScript</option>{capabilities?.build_scripts.map(name=><option key={name} value={name}>{name}</option>)}</Choice></Field>}
                <label className="jj-checkbox"><input type="checkbox" checked={value.allow_install_scripts??false} disabled={disabled} onChange={event=>onChange({...value,allow_install_scripts:event.target.checked})}/><span>允许依赖安装脚本</span></label>
            </div>
            <section className="jj-runtime-databases"><header><div><h4>SQLite 测试数据</h4><p className="jj-small jj-muted">使用独立副本，原数据库保留。</p></div><Button disabled={disabled||databases.length>=4} onClick={()=>add()}>手动添加</Button></header>
            {!!availablePaths.length&&<div className="jj-runtime-database-suggestions"><Field label="使用源码中已有的数据库"><Choice value="" disabled={disabled||databases.length>=4} placeholder="选择数据库，带入已识别的结构" onValueChange={add}>{availablePaths.map(path=><option key={path} value={path}>{path}</option>)}</Choice></Field></div>}
            {databases.map((database,index)=><div className="jj-runtime-database" key={index}>
                <div className="jj-runtime-database-heading"><strong>{database.relative_path||'新数据库'}</strong><Button kind="quiet" disabled={disabled} onClick={()=>{setManual(undefined);onChange({...value,sqlite:databases.filter((_,i)=>i!==index)})}}>移除</Button></div>
                {(!suggestions?.paths.includes(database.relative_path)||manual===index)&&<Field label="数据库文件"><input disabled={disabled} placeholder="例如 data/app.sqlite" value={database.relative_path} onChange={event=>update(index,{...database,relative_path:event.target.value})}/></Field>}
                {database.tables.map((table,tableIndex)=>{
                    const schema=suggestions?.tables.find(item=>item.name===table.table)
                    const changeTable=(next:typeof table)=>update(index,{...database,tables:database.tables.map((item,i)=>i===tableIndex?next:item)})
                    const textField=(label:string,key:keyof typeof table)=><Field key={key} label={label}><input disabled={disabled} value={Array.isArray(table[key])?(table[key] as string[]).join(', '):table[key]} onChange={event=>changeTable({...table,[key]:key==='fields'?event.target.value.split(',').map(x=>x.trim()).filter(Boolean):event.target.value})}/></Field>
                    const pickTable=<Field label="业务数据表"><Choice disabled={disabled} value={table.table} onValueChange={name=>{const next=suggestions!.tables.find(item=>item.name===name)!;changeTable({table:name,resource_column:next.primary_key??'',owner_column:'',fields:[]})}}>{suggestions?.tables.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</Choice></Field>
                    const complete=Boolean(table.table&&table.resource_column&&table.owner_column&&table.fields.length)
                    return <div key={tableIndex}>{manual!==index&&complete?<dl className="jj-facts is-stacked jj-runtime-data-summary"><div><dt>业务数据表</dt><dd>{table.table}</dd></div><div><dt>记录编号</dt><dd>{table.resource_column}</dd></div><div><dt>数据所有者</dt><dd>{table.owner_column}</dd></div><div><dt>核对的业务数据</dt><dd>{table.fields.join('、')}</dd></div></dl>:manual!==index&&suggestions?.tables.length?<>
                        {pickTable}
                        {schema?<><div className="jj-runtime-table-fields">
                            <Field label="记录编号"><Choice disabled={disabled} value={table.resource_column} onValueChange={column=>changeTable({...table,resource_column:column,owner_column:table.owner_column===column?'':table.owner_column,fields:table.fields.filter(field=>field!==column)})}>{schema.columns.map(column=><option key={column}>{column}</option>)}</Choice></Field>
                            <Field label="哪个字段保存数据所有者"><Choice disabled={disabled} value={table.owner_column} onValueChange={owner=>{
                                const available=schema.columns.filter(column=>column!==table.resource_column&&column!==owner)
                                const retained=table.fields.filter(column=>available.includes(column))
                                changeTable({...table,owner_column:owner,fields:retained.length?retained:available.length===1?available:[]})
                            }}>{schema.columns.filter(column=>column!==table.resource_column).map(column=><option key={column}>{column}</option>)}</Choice></Field>
                        </div><fieldset className="jj-runtime-observed-fields" disabled={disabled}><legend>需要核对的业务数据</legend>{[...new Set([...schema.columns,...table.fields])].filter(column=>column!==table.resource_column&&column!==table.owner_column).map(column=><label className="jj-checkbox" key={column}><input type="checkbox" checked={table.fields.includes(column)} onChange={event=>changeTable({...table,fields:event.target.checked?[...table.fields,column]:table.fields.filter(item=>item!==column)})}/><span>{column}</span></label>)}</fieldset><p className="jj-small jj-muted">结构来自源码，启动后仍会核对数据库中的实际字段。</p></>:<p className="jj-small jj-muted">选择业务数据表后，直接对应编号、所有者与业务字段。</p>}
                    </>:<FormColumns><section className="jj-field-stack"><SectionHeading title="定位业务记录" level={3} appearance="group"/>{textField('数据表','table')}{textField('资源编号字段','resource_column')}{textField('所有者字段','owner_column')}</section><section className="jj-field-stack"><SectionHeading title="核对业务结果" level={3} appearance="group"/>{textField('需观察的业务字段','fields')}<p className="jj-small jj-muted">只填写本次结果需要核对的字段，以逗号分隔。</p></section></FormColumns>}</div>
                })}
                <Button kind="quiet" disabled={disabled} onClick={()=>setManual(manual===index?undefined:index)}>{manual===index?'返回配置摘要':'调整数据对应'}</Button>
            </div>)}
            </section>
            <ServiceDatabaseOptions projectId={projectId} value={value.databases??[]} onChange={databases=>onChange({...value,databases})} disabled={disabled}/>
        </div>
    </details>
}

