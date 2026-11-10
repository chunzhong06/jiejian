/** 原生元素负责实际进度语义；视觉层独立过渡，活动光带不改变完成数。 */
export function Progress({label,value,max=1,active}:{label:string;value?:number;max?:number;active?:boolean}){
  const limit=Number.isFinite(max)&&max>0?max:1
  const actual=value!==undefined&&Number.isFinite(value)?Math.min(limit,Math.max(0,value)):undefined
  return <div className="jj-progress" data-indeterminate={actual===undefined} data-active={active??actual===undefined}>
    <progress className="jj-sr-only" aria-label={label} value={actual} max={limit}/>
    <span className="jj-progress-fill" aria-hidden="true" style={{transform:`scaleX(${actual===undefined?0:actual/limit})`}}/>
    <span className="jj-progress-activity" aria-hidden="true"/>
  </div>
}
