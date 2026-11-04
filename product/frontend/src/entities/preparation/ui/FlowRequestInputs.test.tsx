import {render,screen,fireEvent} from '@testing-library/react'
import {useState} from 'react'
import {expect,it} from 'vitest'
import {FlowRequestInputs} from './FlowRequestInputs'
import {newParameter,type EditableStep} from './flowInputs'

it('输入位置切换和键盘导航保留已填内容，敏感名称改用动态来源',()=>{
  function Editor(){
    const [step,setStep]=useState<EditableStep>({id:'target',method:'GET',path:'/orders',parameters:[{...newParameter('QUERY'),name:'page',value:'2'}]})
    return <FlowRequestInputs step={step} previous={[]} busy={false} onChange={setStep}/>
  }
  render(<Editor/>)
  expect(screen.getByLabelText('发送的值')).toHaveValue('2')
  fireEvent.click(screen.getByRole('tab',{name:'请求头 0'}))
  fireEvent.click(screen.getByRole('button',{name:'添加请求头'}))
  fireEvent.change(screen.getByLabelText('参数名称'),{target:{value:'X-CSRF-Token'}})
  expect(screen.queryByLabelText('发送的值')).not.toBeInTheDocument()
  expect(screen.getByLabelText('敏感值，仅在本次执行内存中传递')).toBeChecked()
  fireEvent.keyDown(screen.getByRole('tab',{name:'请求头 1'}),{key:'Home'})
  expect(screen.getByLabelText('发送的值')).toHaveValue('2')
})
