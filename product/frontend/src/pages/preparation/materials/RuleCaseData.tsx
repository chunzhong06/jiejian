import {useState} from 'react';
import {preparationApi as api,type ActionPreparation} from '../../../entities/preparation/api/preparation';
import {proofSourcesApi} from '../../../entities/preparation/api/proofSources';
import {useRead} from '../../../shared/lib/useRead';
import {Button} from '../../../shared/ui/actions';
import {Field} from '../../../shared/ui/layout';
import {ErrorNote} from '../../../shared/ui/feedback';

export function RuleCaseData({projectId,action,onSaved}:{projectId:string;action:ActionPreparation;onSaved:()=>void}) {
    const state=useRead('rule-data:'+projectId+':'+action.action_id,async()=>{
        const [data,context]=await Promise.all([api.ruleData(projectId),proofSourcesApi.context(projectId,'sources')]);
        return {data,resources:context.resources.filter(item=>item.action_id===action.action_id&&!item.case_specific)};
    });
    const [editing,setEditing]=useState<string>(),[resourceId,setResourceId]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>();
    const rows=action.permissions.filter(rule=>rule.effective_state==='ACTIVE'&&rule.conditions?.resource_states.length).map(rule=>{
        const saved=state.data?.data.find(item=>item.permission.intent_id===rule.intent_id);
        const position=action.assurance_contract.identity_requirements?.permissions.find(item=>item.permission.intent_id===rule.intent_id);
        const owner=action.identity_requirements.slots.find(item=>item.requirement.slot_id===position?.resource_owner_slot_id)?.test_identity_id;
        const base=state.data?.resources.find(item=>item.owner_identity_id===owner);
        return {rule,base,current:saved?.resource_id??base?.resource_id};
    });
    const groups=new Map<string,typeof rows>();
    for(const row of rows){
        const key=JSON.stringify([row.base?.owner_identity_id,row.rule.conditions!.resource_states,row.current]);
        groups.set(key,[...(groups.get(key)??[]),row]);
    }
    if(!rows.length)return null;
    return <section className="jj-rule-data"><h3>不同状态的测试数据</h3>{state.error?<ErrorNote error={state.error} onRetry={state.reload}/>:Array.from(groups,([key,items])=>{
        const {rule,base,current}=items[0];
        return <article key={key}><header><div><strong>状态为 {rule.conditions!.resource_states.join('、')}</strong><p className="jj-small jj-muted">{current?`数据 ${current}，用于 ${items.length} 条规则`:'先确认这项操作的测试数据'}</p></div><Button kind="quiet" disabled={busy||!base?.binding_fingerprint} onClick={()=>{setEditing(key);setResourceId(current??'');setError(undefined);}}>选择数据</Button></header>
            {editing===key&&<div className="jj-rule-data-editor"><Field label={`测试数据编号，用于这 ${items.length} 条规则`}><input value={resourceId} disabled={busy} onChange={event=>setResourceId(event.target.value)}/></Field><Button disabled={busy} onClick={()=>setEditing(undefined)}>取消</Button><Button kind="primary" busy={busy} disabled={!resourceId.trim()||!base?.binding_fingerprint} onClick={async()=>{
                setBusy(true);setError(undefined);
                try{
                    for(const item of items)await api.selectRuleData(projectId,{permission:{intent_id:item.rule.intent_id!,revision:item.rule.revision!,intent_hash:item.rule.intent_hash!},resource_id:resourceId.trim(),owner_identity_id:item.base!.owner_identity_id,expected_binding_fingerprint:item.base!.binding_fingerprint!});
                    setEditing(undefined);
                }catch(value){setError(value);}
                finally{
                    // 逐规则保存可能部分成功；失败时也回读，不能让旧画面掩盖已保存的选择。
                    state.reload();onSaved();setBusy(false);
                }
            }}>使用这份数据</Button></div>}
        </article>;
    })}{Boolean(error)&&<ErrorNote error={error}/>}</section>;
}
