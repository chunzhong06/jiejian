// 页面更新提示沿用右下角通知区；明确点击才刷新，编辑或检查期间保护当前工作。
import { useState } from 'react'
import { Button } from 'antd'
import { CloseOutlined } from '@ant-design/icons'
import type { SystemStatus } from '../../api/system/system'
import { frontendIdentityState } from '../../shared/runtime/buildIdentity'

export function FrontendBuildNotice({identity, blocked, onReload = () => window.location.reload()}: {
  identity: SystemStatus['frontend_identity']; blocked: boolean; onReload?: () => void
}) {
  const [dismissed,setDismissed] = useState<string>()
  if (frontendIdentityState(identity) !== 'UPDATE_AVAILABLE' || dismissed === identity?.build_id) return null
  return <section className="check-activity-toast" aria-label="页面资源更新">
    <div className="check-activity-toast-heading"><span>页面资源有更新</span><Button type="text" aria-label="关闭页面更新提示" icon={<CloseOutlined/>} onClick={() => setDismissed(identity!.build_id!)}/></div>
    <p>{blocked ? '当前有未完成操作或检查，请完成后再刷新页面。' : '当前页面仍使用上一份资源，刷新后可看到新界面。'}</p>
    <div className="check-activity-toast-actions"><Button type="link" disabled={blocked} onClick={() => {if (!blocked) onReload()}}>刷新页面</Button></div>
  </section>
}
