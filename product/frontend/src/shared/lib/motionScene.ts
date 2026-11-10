import {animateMotion,motionDuration,reducedMotion,revealContent,springSample,stopAllMotion,stopMotion} from './motion'
import {pageTransitionActive} from './pageTransition'

const lists='tbody,ul,ol,dl,[data-motion-list],.jj-index-selection,.jj-page,.jj-task-surface-body,.jj-dialog-body,.jj-form-columns-layout,[class$="-list"],[class$="-items"],[class$="-rows"],.jj-account-entities,.jj-registration-targets,.jj-candidate-list,.jj-home-recent'
const readings='.jj-page section,.jj-page article,.jj-dialog-body section,.jj-dialog-body article,.jj-task-surface-body section,.jj-field,[data-motion-content],.jj-task-surface,.jj-inspector,.jj-record-reading,.jj-application-content,.jj-material-detail,.jj-proof-detail,.jj-proof-view-section,.jj-tool-detail,.jj-change-detail,.jj-material-impact,.jj-rule-inspector,.jj-rule-condition-editor,.jj-change-registration,.jj-rule-authoring-panel,.jj-rule-detail-panel,.jj-step-reading,.jj-inspector-content,.jj-settings-content,.jj-runtime-panel,.jj-flow-step,.jj-flow-start,.jj-flow-participants,.jj-flow-confirm,.jj-flow-origin-content,.jj-flow-outcomes,.jj-flow-trial-content,.jj-collaboration-detail,.jj-collaboration-current,.jj-collaboration-context-grid,.jj-collaboration-progress,.jj-update-result,.jj-update-form,.jj-account-detail>article'
const feedback='[data-motion-text],.jj-status,.jj-badge,.jj-result-summary,[data-motion-number],.jj-stage-marker,.jj-choice .ant-select-selection-item,.jj-home-facts strong,.jj-plan-summary,.jj-preparation-progress strong,.jj-home-task-progress>span,.jj-storage-summary strong,.jj-toggle-group>button,.jj-tabs>button,.jj-tabs>a,pre,.jj-heading h1,.jj-object-heading h2,.jj-field>small,.jj-file-error,.jj-file-name'
const arrivals=readings+','+feedback+',[data-motion-icon],.jj-notice,.jj-empty,.jj-loading'
const skipped='[data-selection-indicator],[role=separator],.jj-menu-divider,.jj-sr-only,script,style,.jj-page-skeleton,[hidden],[aria-hidden=true]'
type Box={x:number;y:number;width:number;height:number}
type Moving={x:number;y:number;vx:number;vy:number;duration:number;animation:Animation}
type Tracked={box:Box;moving?:Moving}
const rect=(node:HTMLElement):Box=>{const r=node.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height}}
const visible=(node:HTMLElement)=>node.isConnected&&!node.closest('[hidden],dialog:not([open])')&&node.getClientRects().length>0

/** 只观察展示变化，不接管业务状态。入场、列表补位与状态交接统一编排，轮询相同事实不重播。 */
export function connectMotionScene(root:HTMLElement){
  const tracked=new Map<HTMLElement,Tracked>(),incoming=new Set<HTMLElement>(),states=new Set<HTMLElement>()
  const signatures=new WeakMap<HTMLElement,string>()
  const signature=(node:HTMLElement)=>[node.textContent,node.dataset.tone,node.closest<HTMLElement>('[data-state]')?.dataset.state].join('|')
  let frame=0,resetFrame=0,disposed=false,initial=true
  const preference=matchMedia('(prefers-reduced-motion: reduce)')
  const ownsContent=(node:HTMLElement)=>Boolean(node.closest('[data-motion-owner],[data-motion-arriving],[data-milestone-active]'))
  const inspect=(node:HTMLElement)=>{
    if(node.matches(skipped)&&!node.matches('[data-motion-icon]'))return
    const containers=[...(node.matches(lists)?[node]:[]),...node.querySelectorAll<HTMLElement>(lists)]
    for(const container of containers){
      for(const child of container.children){
        if(!(child instanceof HTMLElement)||child.matches(skipped)||tracked.has(child)||!visible(child))continue
        tracked.set(child,{box:targetBox(child)})
        if(!initial&&!child.matches('thead,tfoot')&&!ownsContent(child))incoming.add(child)
      }
    }
    for(const state of [...(node.matches(feedback)?[node]:[]),...node.querySelectorAll<HTMLElement>(feedback)])if(!signatures.has(state))signatures.set(state,signature(state))
    if(!initial){
      const additions=[...(node.matches(arrivals)?[node]:[]),...node.querySelectorAll<HTMLElement>(arrivals)]
      additions.forEach(item=>{if(!ownsContent(item))incoming.add(item)})
    }
  }
  const sample=(moving:Moving)=>{
    if(moving.animation.playState==='idle')return {x:{position:0,velocity:0},y:{position:0,velocity:0}}
    const t=Number(moving.animation.currentTime??0)/1000
    return {x:springSample(moving.x,0,moving.vx,t,moving.duration),y:springSample(moving.y,0,moving.vy,t,moving.duration)}
  }
  function targetBox(node:HTMLElement){
    const next=rect(node)
    for(let ancestor:HTMLElement|null=node;ancestor;ancestor=ancestor.parentElement){
      const movement=tracked.get(ancestor)?.moving
      if(movement){const offset=sample(movement);next.x-=offset.x.position;next.y-=offset.y.position}
    }
    return next
  }
  const rebase=()=>{
    resetFrame=0
    for(const [node,state] of tracked){
      if(!visible(node)){if(!node.isConnected)tracked.delete(node);continue}
      if(!node.closest('[data-motion-arriving]'))state.box=targetBox(node)
    }
  }
  const scheduleRebase=()=>{if(!resetFrame)resetFrame=requestAnimationFrame(rebase)}
  const flush=()=>{
    frame=0
    if(disposed)return
    if(reducedMotion()||document.visibilityState==='hidden'||pageTransitionActive()){
      incoming.clear();states.clear();rebase();return
    }
    // 先批量读取，再写动画，避免每个条目交替测量和改样式触发布局回流。
    const changes:Array<{node:HTMLElement;state:Tracked;next:Box;bx:number;by:number;dx:number;dy:number;vx:number;vy:number}>=[]
    for(const [node,state] of tracked){
      if(!node.isConnected){tracked.delete(node);stopMotion(node,'position');continue}
      if(!visible(node))continue
      if(node.closest('[data-motion-arriving]'))continue
      const next=targetBox(node),current=state.moving?sample(state.moving):undefined
      const moved=Math.abs(state.box.x-next.x)+Math.abs(state.box.y-next.y)>1
      if(moved&&!incoming.has(node)&&next.y+next.height>scrollY&&next.y<scrollY+innerHeight){
        changes.push({node,state,next,bx:state.box.x-next.x,by:state.box.y-next.y,dx:state.box.x+(current?.x.position??0)-next.x,dy:state.box.y+(current?.y.position??0)-next.y,vx:current?.x.velocity??0,vy:current?.y.velocity??0})
      }
      state.box=next
    }
    const changedByNode=new Map(changes.map(change=>[change.node,change]))
    for(const change of changes){
      const {node,state,vx,vy}=change
      // 父容器已经承担的位移从子项扣除，防止嵌套列表出现双倍移动。
      let ancestor=node.parentElement
      while(ancestor&&!changedByNode.has(ancestor))ancestor=ancestor.parentElement
      const parent=ancestor?changedByNode.get(ancestor):undefined
      const dx=change.dx-(parent?.bx??0),dy=change.dy-(parent?.by??0)
      if(Math.abs(dx)+Math.abs(dy)<.5)continue
      if(Math.abs(dx)+Math.abs(dy)>innerHeight)continue
      const duration=motionDuration(node,'--motion-layout',340),length=duration*1.4
      const frames=Array.from({length:37},(_,i)=>({translate:`${springSample(dx,0,vx,length*i/36000,duration).position}px ${springSample(dy,0,vy,length*i/36000,duration).position}px`,offset:i/36}))
      frames[36]={translate:'0 0',offset:1}
      const animation=animateMotion(node,'position',frames,{duration:length,easing:'linear'})
      state.moving=animation?{x:dx,y:dy,vx,vy,duration,animation}:undefined
      if(animation)void animation.finished.catch(()=>{}).finally(()=>{if(state.moving?.animation===animation)state.moving=undefined})
    }
    const additions=[...incoming].filter(node=>visible(node)&&!ownsContent(node))
    const top=additions.filter(node=>!additions.some(parent=>parent!==node&&parent.contains(node)))
    top.forEach((node,index)=>revealContent(node,Math.min(index*18,72),node.matches('tr')?0:4))
    for(const node of states){
      const next=signature(node),previous=signatures.get(node);signatures.set(node,next)
      if(next===previous)continue
      if(!visible(node)||top.some(parent=>parent.contains(node)||node.contains(parent))||[...states].some(child=>child!==node&&node.contains(child)))continue
      // 状态在所属名称旁就地交接；正文与展开仍沿阅读方向进入，避免所有变化一起上下跳动。
      if(node.matches('.jj-stage-marker')){
        animateMotion(node,'appearance',[{opacity:.55,scale:.86},{opacity:1,scale:1.08,offset:.65},{opacity:1,scale:1}],{duration:motionDuration(node,'--motion-complete',460),easing:'cubic-bezier(.16,1,.3,1)'})
      }else if(node.matches('.jj-status,.jj-badge,[data-motion-number]')){
        animateMotion(node,'appearance',[{opacity:.55},{opacity:1}],{duration:motionDuration(node,'--motion-state',200),easing:'ease-out'})
      }else revealContent(node,0,node.matches('pre,.jj-field>small,.jj-file-error')?3:1,'--motion-state')
    }
    incoming.clear();states.clear()
  }
  inspect(root);initial=false
  const observer=new MutationObserver(records=>{
    let changed=false
    for(const record of records){
      const target=record.target instanceof HTMLElement?record.target:record.target.parentElement
      if(!target||target.closest('[data-motion-ignore]'))continue
      if(record.type==='childList'){
        record.addedNodes.forEach(node=>{if(node instanceof HTMLElement)inspect(node)})
        // 容器本身未新增时，也登记刚加入原生表格、列表或表单组的新条目。
        if(target.matches(lists))inspect(target)
        changed=true
      }else if(record.type==='characterData'||record.type==='attributes'){
        if(record.type==='attributes'&&record.attributeName==='class'&&!target.matches(feedback))continue
        const state=target.closest<HTMLElement>(feedback)
        if(state)states.add(state)
        if(record.attributeName==='data-state')target.querySelectorAll<HTMLElement>('.jj-stage-marker').forEach(marker=>states.add(marker))
        if(record.attributeName==='hidden'&&!target.hidden)inspect(target)
        changed=true
      }
      const state=target.closest<HTMLElement>(feedback)
      if(state)states.add(state)
    }
    if(changed&&!frame)frame=requestAnimationFrame(flush)
  })
  observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','hidden','disabled','aria-busy','aria-expanded','aria-selected','aria-pressed','data-state','data-tone','data-complete','data-active']})
  const halt=()=>{
    document.documentElement.dataset.motionPaused=String(document.visibilityState==='hidden')
    if(preference.matches||document.visibilityState==='hidden'){
      stopAllMotion();for(const state of tracked.values())state.moving=undefined
    }
    scheduleRebase()
  }
  preference.addEventListener('change',halt);document.addEventListener('visibilitychange',halt)
  document.addEventListener('scroll',scheduleRebase,true);window.addEventListener('resize',scheduleRebase)
  void document.fonts?.ready.then(()=>{if(!disposed)scheduleRebase()})
  return()=>{
    disposed=true;observer.disconnect();cancelAnimationFrame(frame);cancelAnimationFrame(resetFrame);stopAllMotion();delete document.documentElement.dataset.motionPaused
    preference.removeEventListener('change',halt);document.removeEventListener('visibilitychange',halt)
    document.removeEventListener('scroll',scheduleRebase,true);window.removeEventListener('resize',scheduleRebase)
  }
}
