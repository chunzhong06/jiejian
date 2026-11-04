import type {Route} from './navigation'

export const settingsSections=[{key:'tools',label:'开发工具'},{key:'storage',label:'本地存储'},{key:'system',label:'运行与维护'}] as const
export type SettingsSection=typeof settingsSections[number]['key']
export function settingsSection(route:Route):SettingsSection|null{
  if(route.path==='/tools'||route.path==='/settings/models')return 'tools'
  if(route.path==='/storage')return 'storage'
  if(route.path==='/system')return 'system'
  if(route.path!=='/settings')return null
  return settingsSections.find(item=>item.key===route.query.get('section'))?.key??'tools'
}
export function settingsPath(section:SettingsSection,view?:string){return '/settings?section='+section+(view?'&view='+encodeURIComponent(view):'')}
