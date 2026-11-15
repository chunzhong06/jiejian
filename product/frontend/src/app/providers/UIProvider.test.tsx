import {useState} from 'react'
import {act,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {UIProvider} from './UIProvider'

vi.mock('../../shared/ui/MotionRoot',()=>({MotionRoot:()=>null}))
afterEach(()=>vi.unstubAllGlobals())

it.each([false,true])('初始减少动态效果为%s时，切换系统偏好与主题都保留子任务草稿',initial=>{
 const listeners=new Set<()=>void>()
 const preference={matches:initial,media:'(prefers-reduced-motion: reduce)',addEventListener:(_type:string,listener:()=>void)=>listeners.add(listener),removeEventListener:(_type:string,listener:()=>void)=>listeners.delete(listener)}
 vi.stubGlobal('matchMedia',(query:string)=>query===preference.media?preference:{...preference,matches:false})
 function Editor(){const [value,setValue]=useState('');return <input aria-label="当前任务草稿" value={value} onChange={event=>setValue(event.target.value)}/>}
 const view=render(<UIProvider appearance="light"><Editor/></UIProvider>)
 const input=screen.getByRole('textbox',{name:'当前任务草稿'})
 fireEvent.change(input,{target:{value:'继续同一份业务说明'}})
 for(const reduced of [!initial,initial,!initial]){
  act(()=>{preference.matches=reduced;listeners.forEach(listener=>listener())})
  expect(screen.getByRole('textbox',{name:'当前任务草稿'})).toBe(input)
  expect(input).toHaveValue('继续同一份业务说明')
 }
 view.rerender(<UIProvider appearance="dark"><Editor/></UIProvider>)
 expect(screen.getByRole('textbox',{name:'当前任务草稿'})).toBe(input)
 expect(input).toHaveValue('继续同一份业务说明')
})
