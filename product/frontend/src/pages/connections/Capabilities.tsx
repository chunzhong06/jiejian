import CheckOutlined from '@ant-design/icons/CheckOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { projectsApi } from '../../entities/application/api/projects';
import { useRead } from '../../shared/lib/useRead';
import { assertProject } from '../../shared/model/page';
import {scopedPath} from '../../shared/lib/navigation'
import { Badge, ErrorNote } from '../../shared/ui/feedback';
import {ActionLink} from '../../shared/ui/actions'

const tasks: Record<string,{title:string;ready:string;pending:string}> = {
    source:{title:'读取业务内容',ready:'已识别源码中的角色和操作',pending:'需要从源码识别角色和操作时，在左侧允许读取'},
    endpoint:{title:'连接应用',ready:'上次连接检查可以访问',pending:'在左侧设置应用的访问地址'},
    runtime:{title:'核对运行代码',ready:'已保存对应源码的运行记录',pending:'核验源码修改时，由界鉴启动并记录对应代码'},
    proof:{title:'准备结果判断依据',ready:'已有配置，检查前还会核对是否可用',pending:'在材料准备中选择如何确认业务结果'},
};
export function Capabilities({projectId, revision}: {projectId:string;revision:number}) {
    const state=useRead('readiness:'+projectId+':'+revision,async signal=>{const value=await projectsApi.readiness(projectId,signal);assertProject(value.project_id,projectId);return value;});
    const connected=state.data?.items.find(item=>item.key==='endpoint')?.state==='READY';
    return <aside className="jj-application-capabilities" aria-label="源码的后续用途">
      <header><h2 className="jj-title-group">这份源码用于什么</h2></header>
      {state.error&&<ErrorNote error={state.error}/>}
      {state.loading&&!state.data?<p className="jj-small jj-muted">正在读取接入状态</p>:<ul>{state.data?.items.filter(item=>['source','runtime'].includes(item.key)).map(item=>{
        const available=['READY','AVAILABLE','CONFIGURED'].includes(item.state),task=tasks[item.key];
        return <li key={item.key} data-ready={item.state==='READY'}>
          <span className="jj-capability-marker" aria-hidden="true">{item.state==='READY'&&<CheckOutlined/>}</span>
          <div className="jj-object-line"><h3>{task?.title??item.label}</h3><Badge tone={item.state==='READY'?'positive':'neutral'}>{({READY:'已确认',AVAILABLE:'已有记录',CONFIGURED:'已有配置',NEEDS_ACTION:'待准备',UNVERIFIED:'待核对'} as Record<string,string>)[item.state]??'待核对'}</Badge></div>
          <p>{task?(available?task.ready:task.pending):item.detail}</p>
        </li>
      })}</ul>}
      {connected&&<footer><ActionLink navigationScope="page" href={'#'+scopedPath('/preparation',projectId)}>查看检查材料<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer>}
    </aside>;
}
