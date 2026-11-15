import type {CollaborationTask} from '../../entities/runtime/api/collaboration'
import {collaborationOutputs} from '../../entities/runtime/model/taskReading'
import {ObjectTable} from '../../shared/ui/ObjectTable'

export function CollaborationObjective({task}:{task:CollaborationTask}){
 const outputs=collaborationOutputs(task)
 return <>{task.brief?.objective&&<p className="jj-collaboration-objective">{task.brief.objective}</p>}
  {outputs.length>0&&<details className="jj-collaboration-deliverables"><summary>{task.brief?.outputs.length?'本次交付目标':'本次保存内容'} · {outputs.length} 项</summary>
   <ObjectTable selection="" aria-label="本次交付与保存记录"><thead><tr><th>内容</th><th>本任务的保存记录</th></tr></thead><tbody>{outputs.map((output,index)=><tr key={output.kind+':'+index}><th scope="row">{output.label}</th><td>{output.saved?'已保存 '+output.saved+' 份':'尚无保存记录'}</td></tr>)}</tbody></ObjectTable>
   <p className="jj-small jj-muted">保存记录用于核对产物；采用与检查结果在对应工作面查看。</p>
  </details>}
 </>
}
