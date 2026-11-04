import SettingOutlined from '@ant-design/icons/SettingOutlined'
import {go} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {preloadRoute} from '../Router'

export function SettingsEntry({current,projectId,onNavigate}:{current:string;projectId?:string;onNavigate:()=>void}){
  const selected=['/settings','/tools','/storage','/system'].includes(current)
  return <Button kind="quiet" className="jj-nav-item jj-settings-entry" icon={<SettingOutlined aria-hidden="true"/>} aria-label="设置" aria-current={selected?'page':undefined} onPointerEnter={()=>preloadRoute('/settings')} onFocus={()=>preloadRoute('/settings')} onClick={()=>{go('/settings',projectId);onNavigate()}}><span className="jj-nav-label" data-short="true">设置</span></Button>
}
