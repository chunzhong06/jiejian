import {flushSync} from 'react-dom'
import {stopMotion} from './motion'

let active:ViewTransition|null=null
let releaseReading:(()=>void)|undefined

export function pageTransitionActive(){return active!==null}

function commit(update:()=>void,direction='forward'){
  // 新导航立即接管旧快照，不排队播放；完成回调也只能清理自己仍拥有的过渡状态。
  stopMotion(document.documentElement,'appearance')
  active?.skipTransition()
  releaseReading?.()
  if(!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches){
    active=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
    update()
    return
  }
  document.documentElement.dataset.visualTransition='page'
  document.documentElement.dataset.pageDirection=direction
  // 同步提交 React 路由后再取新快照；数据尚未就绪时的内容出现由 PageSurface 单独处理。
  const next=document.startViewTransition(()=>flushSync(update))
  active=next
  observeInterruption(next)
  void next.ready.catch(()=>{})
  void next.finished.catch(()=>{}).finally(()=>{if(active===next){
    active=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
  }})
}
export const commitPageTransition=(update:()=>void,direction='forward')=>commit(update,direction)

function observeInterruption(next:ViewTransition){
  const preference=matchMedia('(prefers-reduced-motion: reduce)')
  const stop=()=>{if(preference.matches||document.visibilityState==='hidden')next.skipTransition()}
  preference.addEventListener('change',stop);document.addEventListener('visibilitychange',stop)
  void next.finished.catch(()=>{}).finally(()=>{preference.removeEventListener('change',stop);document.removeEventListener('visibilitychange',stop)})
}

/** 仅公开目录过滤使用浏览器绘制快照退场；业务节点立即提交，编辑与秘密区域直接更新。 */
export function commitReadingTransition(root:HTMLElement|null,update:()=>void){
  if(!root||!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches||root.querySelector('input,textarea,pre,[data-sensitive]')){update();return}
  active?.skipTransition();releaseReading?.()
  const page=root.closest<HTMLElement>('.jj-page'),names=new Map<HTMLElement,string>()
  const name=(node:HTMLElement,value:string)=>{names.set(node,node.style.viewTransitionName);node.style.viewTransitionName=value}
  if(page&&page!==root)name(page,'none')
  name(root,'jj-reading')
  const used=new Set<string>()
  for(const row of Array.from(root.querySelectorAll<HTMLElement>('[data-directory-id],[data-case]')).slice(0,32)){
    const key=row.dataset.directoryId??row.dataset.case??''
    let hash=2166136261;for(const letter of key)hash=Math.imul(hash^letter.charCodeAt(0),16777619)
    const id='jj-row-'+(hash>>>0).toString(16)
    if(used.has(id))continue;used.add(id);name(row.closest<HTMLElement>('tr,article')??row,id)
  }
  let released=false
  const release=()=>{if(released)return;released=true;for(const [node,previous] of names)node.style.viewTransitionName=previous;if(releaseReading===release)releaseReading=undefined}
  releaseReading=release
  document.documentElement.dataset.visualTransition='reading'
  const next=document.startViewTransition(()=>flushSync(update));active=next;observeInterruption(next)
  void next.ready.catch(()=>{})
  void next.finished.catch(()=>{}).finally(()=>{release();if(active===next){active=null;delete document.documentElement.dataset.visualTransition}})
}

export function commitThemeTransition(update:()=>void){
  active?.skipTransition();active=null
  releaseReading?.()
  stopMotion(document.documentElement,'appearance')
  delete document.documentElement.dataset.visualTransition
  delete document.documentElement.dataset.pageDirection
  flushSync(update)
  // 主题颜色由共享 CSS 接续；整窗再淡入会叠加亮度波动，并让每个表面重复反馈。
}
