export type Route={path:string;query:URLSearchParams}
export function readRoute():Route{const [path,query]=(location.hash.slice(1)||'/workspace').split('?');return {path,query:new URLSearchParams(query)}}
export function go(path:string){location.hash=path}
export function historyLocation(projectId?:string){
  if(!projectId)return '/reports'
  try{const saved=sessionStorage.getItem('jiejian.studio.history-location:'+projectId);if(saved?.startsWith('/reports')&&!new URLSearchParams(saved.split('?')[1]).has('run_id'))return saved}catch{}
  return '/reports'
}
