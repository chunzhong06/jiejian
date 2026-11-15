import {Button} from '../../../shared/ui/actions'
import './agent-assist.css'

const actions={flow:'补全接口流程',proof:'补全证明配置',sources:'整理结果证明',scenario:'整理业务场景',preparation:'协助准备',report:'解读本次结果',repair:'协助修复'}

/** 协作辅助入口共用弱操作与具名目标；交接范围、确认和执行继续由原调用者持有。 */
export function AgentAssistAction({task,disabled,onClick}:{task:keyof typeof actions;disabled?:boolean;onClick:()=>void}){
 return <Button kind="quiet" className="jj-agent-assist" data-agent-assist={task} disabled={disabled} onClick={onClick}>请 Agent {actions[task]}</Button>
}
