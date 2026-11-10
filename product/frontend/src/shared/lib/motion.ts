import {motionMilliseconds} from './motionTiming'

type Channel='appearance'|'position'|'size'|'overlay'|'selection'
type Active={node:HTMLElement;channel:Channel;animation:Animation}
const active=new Set<Active>()
const owners=new WeakMap<HTMLElement,Map<Channel,Active>>()

export const reducedMotion=()=>typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches
export function motionDuration(node:Element,token:string,fallback=240){
  return motionMilliseconds(getComputedStyle(node).getPropertyValue(token),fallback)
}

/** 同一属性只有一个运动所有者；调用者先取得当前视觉值，再交接到新目标。 */
export function animateMotion(node:HTMLElement,channel:Channel,frames:Keyframe[],options:KeyframeAnimationOptions){
  stopMotion(node,channel)
  if(!node.animate||reducedMotion()||document.visibilityState==='hidden')return undefined
  const animation=node.animate(frames,options),entry={node,channel,animation}
  const slots=owners.get(node)??new Map<Channel,Active>();owners.set(node,slots);slots.set(channel,entry);active.add(entry)
  void animation.finished.catch(()=>{}).finally(()=>{
    active.delete(entry)
    if(slots.get(channel)===entry)slots.delete(channel)
    // 终态由真实DOM/CSS拥有，释放fill层，避免完成后的动画长期遮住后续状态。
    if(animation.playState==='finished')animation.cancel()
  })
  return animation
}
export function stopMotion(node:HTMLElement,channel:Channel){
  const entry=owners.get(node)?.get(channel)
  if(entry){entry.animation.cancel();active.delete(entry);owners.get(node)?.delete(channel)}
}
export function stopAllMotion(){
  for(const entry of active){entry.animation.cancel();owners.get(entry.node)?.delete(entry.channel)}
  active.clear()
}

/** 归一化弹簧同时返回位置与速度，快速改向不会把新动作重置为静止。 */
export function springSample(from:number,target:number,velocity:number,seconds:number,duration:number,damping=.86){
  const frequency=8/(duration/1000),delta=from-target,t=Math.max(0,seconds)
  if(damping>=1){
    const impulse=velocity+frequency*delta,decay=Math.exp(-frequency*t)
    return {position:target+(delta+impulse*t)*decay,velocity:(impulse-frequency*(delta+impulse*t))*decay}
  }
  const decayRate=damping*frequency,oscillation=frequency*Math.sqrt(1-damping*damping)
  const b=(velocity+decayRate*delta)/oscillation,decay=Math.exp(-decayRate*t),cos=Math.cos(oscillation*t),sin=Math.sin(oscillation*t)
  const wave=delta*cos+b*sin
  return {position:target+decay*wave,velocity:decay*((-delta*oscillation*sin+b*oscillation*cos)-decayRate*wave)}
}

export function revealContent(node:HTMLElement,delay=0,distance=5,token='--motion-content'){
  const opacity=getComputedStyle(node).opacity
  const interrupted=owners.get(node)?.has('appearance')
  animateMotion(node,'appearance',[{opacity:interrupted?opacity:.76},{opacity:1}],{duration:motionDuration(node,token,240),delay,easing:'cubic-bezier(.16,1,.3,1)'})
  // 独立 translate 不覆盖按钮按压的 transform，也不改变布局尺寸。
  node.dataset.motionArriving='true'
  const movement=animateMotion(node,'position',[{translate:`0 ${distance}px`},{translate:'0 0'}],{duration:motionDuration(node,token,240),delay,easing:'cubic-bezier(.16,1,.3,1)'})
  if(movement)void movement.finished.catch(()=>{}).finally(()=>{
    const current=owners.get(node)?.get('position')?.animation
    if(!current||current===movement)delete node.dataset.motionArriving
  })
  else delete node.dataset.motionArriving
}

export function revealPage(node:HTMLElement){
  node.dataset.motionArriving='true'
  const groups=Array.from(node.children).filter((item):item is HTMLElement=>item instanceof HTMLElement&&!item.hidden&&item.getClientRects().length>0)
  if(!groups.length){revealContent(node);delete node.dataset.motionArriving;return}
  groups.forEach((group,index)=>revealContent(group,Math.min(index*18,72),6))
  const last=owners.get(groups[groups.length-1])?.get('appearance')?.animation
  if(last)void last.finished.catch(()=>{}).finally(()=>{delete node.dataset.motionArriving})
  else delete node.dataset.motionArriving
}

/** 原生模态层维持命中与焦点约束，关闭从此刻的视觉位置继续，结束后才释放模态层。 */
export function animateOverlay(node:HTMLElement,closing=false){
  const style=getComputedStyle(node),wasMoving=owners.get(node)?.has('overlay')
  const from=wasMoving?{opacity:style.opacity,transform:style.transform}:closing?{opacity:1,transform:'none'}:{opacity:.4,transform:'translateY(10px) scale(.985)'}
  return animateMotion(node,'overlay',[from,closing?{opacity:0,transform:'translateY(5px) scale(.99)'}:{opacity:1,transform:'none'}],{
    duration:motionDuration(node,closing?'--motion-exit':'--motion-dialog',closing?180:340),easing:closing?'cubic-bezier(.4,0,1,1)':'cubic-bezier(.16,1,.3,1)',fill:'both',
  })
}
