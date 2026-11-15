import type {ReactNode} from 'react';
import { projectsApi } from '../../entities/application/api/projects';
import { useRead } from '../../shared/lib/useRead';
import { assertProject } from '../../shared/model/page';
import {scopedPath} from '../../shared/lib/navigation'
import { Badge, ErrorNote } from '../../shared/ui/feedback';
import {ActionLink} from '../../shared/ui/actions'
import {ObjectHeading,TaskActions} from '../../shared/ui/layout'
import {ValidationPlanPanel} from '../../entities/permission/ui/ValidationPlan'

const tasks: Record<string,{title:string;ready:string;pending:string}> = {
    source:{title:'源码中的业务',ready:'已识别源码中的角色和操作',pending:'允许读取源码后，可以识别角色和操作线索'},
    runtime:{title:'核对运行代码',ready:'已保存对应源码的运行记录',pending:'核验源码修改时，由界鉴启动并记录对应代码'},
};
/** 用途、准备事实和原操作同组；读取状态失败不移除父页已有的配置与授权操作。 */
export function Capabilities({projectId, revision,sourceControls,runtimeControls}: {projectId:string;revision:number;sourceControls:ReactNode;runtimeControls?:ReactNode}) {
    const state=useRead('readiness:'+projectId+':'+revision,async signal=>{const value=await projectsApi.readiness(projectId,signal);assertProject(value.project_id,projectId);return value;});
    const connected=state.data?.items.find(item=>item.key==='endpoint')?.state==='READY';
    return <div className="jj-application-capabilities">
      {state.error&&<ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取接入能力"/>}
      <div className="jj-source-uses">{(['source','runtime'] as const).map(key=>{
        const item=state.data?.items.find(item=>item.key===key),available=item&&['READY','AVAILABLE','CONFIGURED'].includes(item.state),task=tasks[key];
        return <section className="jj-source-use" key={key} aria-label={task.title}>
          <ObjectHeading level={3} title={task.title} status={item&&<Badge tone={item.state==='READY'?'positive':'neutral'}>{({READY:key==='source'?'已识别':'已确认',AVAILABLE:'已有记录',CONFIGURED:'已有配置',NEEDS_ACTION:'待准备',UNVERIFIED:'待核对'} as Record<string,string>)[item.state]??'待核对'}</Badge>}/>
          <p>{item?(available?task.ready:task.pending):state.loading?'正在读取接入状态':'接入状态尚未确认，请重新读取后核对。'}</p>
          <div className="jj-source-use-controls">{key==='source'?sourceControls:runtimeControls}</div>
        </section>
      })}</div>
      <ValidationPlanPanel projectId={projectId} mode="summary"/>
      {connected&&<TaskActions><ActionLink kind="primary" navigationScope="page" href={'#'+scopedPath('/preparation',projectId)}>继续核对检查材料</ActionLink></TaskActions>}
    </div>;
}
