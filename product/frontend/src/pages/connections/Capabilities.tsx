import { projectsApi } from '../../entities/application/api/projects';
import { useRead } from '../../shared/lib/useRead';
import { assertProject } from '../../shared/model/page';
import { go } from '../../shared/lib/navigation';
import { Badge, ErrorNote } from '../../shared/ui/feedback';
import { Button } from '../../shared/ui/actions';

export function Capabilities({projectId, revision}: {projectId:string;revision:number}) {
    const state=useRead('readiness:'+projectId+':'+revision,async signal=>{const value=await projectsApi.readiness(projectId,signal);assertProject(value.project_id,projectId);return value;});
    return <section className="jj-application-capabilities" aria-label="应用接入能力">
      <header><h2>检查条件</h2></header>
      {state.error&&<ErrorNote error={state.error} onRetry={state.reload}/>}
      {state.loading&&!state.data?<p className="jj-small jj-muted">正在读取接入条件</p>:<div>{state.data?.items.map(item=><article key={item.key}><div className="jj-item-heading"><h3>{item.label}</h3><Badge tone={item.state==='READY'?'positive':'neutral'}>{({READY:'已核对',AVAILABLE:'已有记录',CONFIGURED:'已配置',NEEDS_ACTION:'待准备',UNVERIFIED:'待核验'} as Record<string,string>)[item.state]??'待核验'}</Badge></div>{(item.key==='proof'||['NEEDS_ACTION','UNVERIFIED'].includes(item.state))&&<p className="jj-small jj-muted">{item.detail}</p>}{item.key==='proof'&&<Button kind="quiet" onClick={()=>go(item.destination,projectId)}>准备业务证明</Button>}</article>)}</div>}
    </section>;
}
