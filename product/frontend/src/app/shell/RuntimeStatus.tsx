import {ReloadOutlined} from '@ant-design/icons'
import {systemApi} from '../../entities/runtime/api/system'
import {useRead} from '../../shared/lib/useRead'
import {Button} from '../../shared/ui/actions'
import {ErrorNote} from '../../shared/ui/feedback'
import {InfoPopover} from '../../shared/ui/InfoPopover'

export function RuntimeStatus(){
  const state=useRead('system',systemApi.status,10000)
  const ready=!state.error&&state.data?.api==='available'&&state.data.worker==='running'&&state.data.browser==='available'
  const label=state.error?'运行状态未知':!state.data?'正在核对服务':ready?'本地服务运行中':'运行环境需检查'
  return <InfoPopover label="本地运行环境"
    actions={<Button kind="quiet" className="jj-system-refresh" busy={state.loading} aria-label="刷新运行状态" icon={<ReloadOutlined aria-hidden="true"/>} onClick={state.reload}/>}
    trigger={<Button kind="quiet" className="jj-system-state"><i aria-hidden="true" className={ready?'is-ready':''}/><span>{label}</span></Button>}>
    <dl className="jj-system-facts">
      <div><dt>界鉴版本</dt><dd>{state.data?.version??'正在读取'}</dd></div>
      <div><dt>执行服务</dt><dd>{!state.error&&state.data?.worker==='running'?'可用':'待确认'}</dd></div>
      <div><dt>检查浏览器</dt><dd>{!state.error&&state.data?.browser==='available'?'可用':'待确认'}</dd></div>
    </dl>
    {state.error&&<ErrorNote error={state.error}/>}
  </InfoPopover>
}
