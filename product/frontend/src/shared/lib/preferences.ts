type PreferenceKey='jiejian.studio.theme'|'jiejian.studio.project'
const memory=new Map<PreferenceKey,string>()
const unsaved=new Set<PreferenceKey>()

/** 非秘密显示偏好可退回文档内存；不用于命令回执或业务数据恢复。 */
export function readPreference(key:PreferenceKey):string|null{
  if(unsaved.has(key))return memory.get(key)??null
  try{return localStorage.getItem(key)}catch{return memory.get(key)??null}
}
export function writePreference(key:PreferenceKey,value:string){
  memory.set(key,value)
  try{localStorage.setItem(key,value);unsaved.delete(key)}catch{unsaved.add(key)}
}
