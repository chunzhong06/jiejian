export function text(value:string){return value.replace(/\s*·\s*/g,'，')}
export function date(value:number){return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(value/1000)}
