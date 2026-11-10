import {useEffect} from 'react'
import {connectMotionScene} from '../lib/motionScene'

/** 单一展示观察者覆盖正文、原生控件和Portal；卸载时清理监听与活动动画。 */
export function MotionRoot(){
  useEffect(()=>connectMotionScene(document.body),[])
  return null
}
