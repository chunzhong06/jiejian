/** 构建器可以把 ms 压缩成 s；原生动画和计时器统一接收毫秒。 */
export function motionMilliseconds(token:string,fallback=0){
  const time=token.trim().match(/^(\d*\.?\d+)(ms|s)$/)
  return time?Number(time[1])*(time[2]==='s'?1000:1):fallback
}
