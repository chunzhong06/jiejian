import {routes,routeAliases,routeDefinition} from './routes'
import type {Route} from './navigation'

export const settingsSections=routes.filter((item):item is typeof item & {settings:'tools'|'storage'|'system'}=>item.settings!==undefined).map(item=>({key:item.settings,label:item.label}))
export type SettingsSection=typeof settingsSections[number]['key']
export function settingsSection(route:Route):SettingsSection|null{
  const legacy=routeDefinition(routeAliases[route.path]??route.path)?.settings
  if(legacy)return legacy
  if(route.path!=='/settings')return null
  return settingsSections.find(item=>item.key===route.query.get('section'))?.key??'tools'
}
export function settingsPath(section:SettingsSection,view?:string){return '/settings?section='+section+(view?'&view='+encodeURIComponent(view):'')}
