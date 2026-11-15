import {useState} from 'react'
import type {BoundaryMaintenanceCommandDto} from '../api/businessBoundaries'
import {ValidationPlanPanel} from './ValidationPlan'
import {Button} from '../../../shared/ui/actions'

/** 显式评估一份编辑快照；逐字输入不触发整份准备重读。 */
export function DraftValidationPreview({projectId,command}:{projectId:string;command:BoundaryMaintenanceCommandDto}){
  const [snapshot,setSnapshot]=useState<BoundaryMaintenanceCommandDto>()
  const changed=Boolean(snapshot&&JSON.stringify(snapshot)!==JSON.stringify(command))
  return <details className="jj-draft-validation"><summary>核对调整后的验证方式</summary><div>
    {changed&&<p>编辑内容已变化。下方保留上次评估，继续前请按当前内容重新核对。</p>}
    <Button kind="quiet" onClick={()=>setSnapshot(command)}>{snapshot?'按当前内容重新核对':'评估当前编辑'}</Button>
    {snapshot&&<ValidationPlanPanel projectId={projectId} command={snapshot}/>}
  </div></details>
}
