import type {AdoptionPreview,ProofContext,ProofSource} from '../../../entities/preparation/api/proofSources'
import type {ReactNode} from 'react'
import {text} from '../../../shared/lib/format'
import {scopedPath} from '../../../shared/lib/navigation'
import {ActionLink} from '../../../shared/ui/actions'
import {Badge} from '../../../shared/ui/feedback'
import {ObjectHeading,SectionHeading,TaskStage} from '../../../shared/ui/layout'

type Props={context:ProofContext;source:ProofSource;resource:ProofContext['resources'][number]|undefined;adoption:AdoptionPreview|undefined;mode:'scope'|'adoption';scope:boolean;title:string;method:string;confirmation?:ReactNode;actions?:ReactNode}

/** 授权常显准确读取边界；采用先解释业务用途和影响，再深入原读取范围。确认命令仍由来源工作面拥有。 */
export function SourceReview({context,source,resource,adoption,mode,scope,title,method,confirmation,actions}:Props){
    const resourceIds=mode==='adoption'&&adoption?[adoption.resource_id]:[resource?.resource_id,...context.resources.filter(item=>item.action_id===source.config.action_id&&item.case_specific).map(item=>item.resource_id)].filter(Boolean)
    return <>
        <TaskStage className="jj-source-review-stage" context={<>
            <ObjectHeading title={text(title)} description={method} status={<Badge tone={mode==='scope'&&scope?'positive':'neutral'}>{mode==='scope'?(scope?'已允许读取':'等待授权'):'待确认使用'}</Badge>}/>
                <section className="jj-source-review-group" aria-label="本次证明的业务对象">
                    <SectionHeading title={mode==='scope'?'核对业务对象':'将用于核对的对象'} level={3} appearance="group"/>
                    <dl className="jj-facts">
                        <div><dt>读取账号</dt><dd>{source.config.identity_claims.map(claim=>context.identities.find(item=>item.identity_id===claim.identity_id)?.label??'未找到对应账号').map(text).join('、')||'尚未配置身份核对'}</dd></div>
                        <div><dt>测试资源</dt><dd>{[...new Set(resourceIds)].join('、')||'测试数据已有变化'}</dd></div>
                        <div><dt>资源所有者</dt><dd>{text(context.identities.find(item=>item.identity_id===resource?.owner_identity_id)?.label??'尚未确认')}</dd></div>
                        {mode==='adoption'&&adoption?.expected_state&&<div><dt>需要核对的业务状态</dt><dd>{text(adoption.expected_state)}</dd></div>}
                        {mode==='adoption'&&Boolean(adoption?.protected_projection.length)&&<div><dt>用于判断的字段</dt><dd>{adoption!.protected_projection.map(text).join('、')}</dd></div>}
                    </dl>
                </section>
        </>}>
                {mode==='scope'?<section className="jj-source-review-group" aria-label="本次允许读取的范围"><SectionHeading title="本次允许读取" level={3} appearance="group"/><SourceReadLimits context={context} source={source}/></section>:
                    adoption&&<section className="jj-source-review-group" aria-label="确认使用后的变化">
                        <SectionHeading title="确认使用后的变化" level={3} appearance="group"/>
                        <p>{adoption.replaces_existing?'替换当前对应的证明材料。':'建立这项业务结果的证明材料。'}</p>
                        {adoption.retained.length>0&&<div className="jj-source-impact-group"><h4>继续保留</h4><ul>{adoption.retained.map((item,index)=><li key={index}>{text(item)}</li>)}</ul></div>}
                        {adoption.recheck.length>0&&<div className="jj-source-impact-group"><h4>需要重新核对</h4><ul>{adoption.recheck.map((item,index)=><li key={index}>{text(item)}</li>)}</ul></div>}
                    </section>}
            {confirmation&&<div className="jj-source-confirmation">{confirmation}</div>}
            {actions}
        </TaskStage>
            {mode==='adoption'&&<details className="jj-source-review-details"><summary>本次来源的读取范围</summary><SourceReadLimits context={context} source={source}/></details>}
    </>
}

function SourceReadLimits({context,source}:Pick<Props,'context'|'source'>){
    const config=source.config
    return <dl className="jj-facts">
        <div><dt>应用地址</dt><dd>{context.runtime_origin??'当前运行地址尚未确认'}{!context.runtime_origin&&<ActionLink navigationScope="page" href={'#'+scopedPath('/application?'+new URLSearchParams({view:'environment',return_to:'/preparation?'+new URLSearchParams({action_id:config.action_id,proof_sources:'1',source_id:source.source_id})}),context.project_id)}>核对应用连接</ActionLink>}</dd></div>
        {config.database_capture&&<><div><dt>数据库连接</dt><dd>{config.database_capture.engine} · {config.database_capture.host}:{config.database_capture.port} / {config.database_capture.database}</dd></div><div><dt>数据库账号</dt><dd>{config.database_capture.username}</dd></div><div><dt>数据表与读取字段</dt><dd>{config.database_capture.namespace}.{config.database_capture.table} / {[config.database_capture.resource_column,config.database_capture.owner_column,...config.database_capture.fields].join('、')}</dd></div></>}
        {['SQLITE_AUDIT','SQLITE_OBJECTS'].includes(config.source_kind)?<><div><dt>测试数据库</dt><dd className="jj-path">{config.database_path}</dd></div><div><dt>数据表与读取字段</dt><dd>{config.table} / {[config.resource_column,config.owner_column,...(config.observed_columns??[config.protected_column])].join('、')}</dd></div></>:config.relative_path_template&&<div><dt>结果记录位置</dt><dd className="jj-path">{config.relative_path_template}</dd></div>}
        {[...new Set(config.identity_claims.map(item=>item.request_path).filter(Boolean))].map(path=><div key={path}><dt>身份核对位置</dt><dd className="jj-path">{path}</dd></div>)}
        {config.collection&&<div><dt>记录集合</dt><dd>{config.collection}</dd></div>}
        {config.async_export&&<><div><dt>任务状态位置</dt><dd className="jj-path">{config.async_export.status_path_template}</dd></div><div><dt>文件交付位置</dt><dd className="jj-path">{config.async_export.file_path_template}</dd></div><div><dt>异步等待范围</dt><dd>最多 {config.async_export.max_polls} 次，{config.async_export.timeout_us/1000000} 秒</dd></div></>}
        <div><dt>单次读取限制</dt><dd>{Math.ceil(config.max_response_bytes/1024)} KiB，{config.timeout_us/1000000} 秒</dd></div>
    </dl>
}
