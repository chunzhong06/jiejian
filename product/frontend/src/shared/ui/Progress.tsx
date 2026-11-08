/** 保留原生进度语义；未提供 value 时只表达活动中，不生成估计百分比。 */
export function Progress({label,value,max=1}:{label:string;value?:number;max?:number}){
  return <progress className="jj-progress" aria-label={label} value={value} max={Math.max(1,max)}/>
}
