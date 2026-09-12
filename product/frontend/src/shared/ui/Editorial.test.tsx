// 验证流程只展开指定当前项，AI 采用草稿不会成为权限批准。
import {fireEvent, render, screen} from '@testing-library/react'
import {expect, it, vi} from 'vitest'
import {FlowSpine, MarginNote} from './Editorial'
it('保留完成和未来标题，只展开权威当前项', () => {
  render(<FlowSpine label="动作准备" steps={[
    {key:'a',title:'账号仍有效',state:'complete',detail:<button>重做账号</button>},
    {key:'b',title:'补充结果证明',state:'current',detail:<button>定位当前证明</button>},
    {key:'c',title:'运行检查',state:'future',detail:<button>提前检查</button>},
  ]}/>)
  expect(screen.getByRole('heading',{name:'账号仍有效'})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'定位当前证明'})).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'重做账号'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'提前检查'})).not.toBeInTheDocument()
  expect(document.querySelectorAll('[aria-current="step"]')).toHaveLength(1)
})
it('建议始终标注依据与尚未生效，采用只调用草稿回调', () => {
  const adopt=vi.fn();render(<MarginNote basis="用户提供的业务描述" onAdopt={adopt}><p>保护完整交付包</p></MarginNote>)
  fireEvent.click(screen.getByRole('button',{name:'采用到草稿'}))
  expect(adopt).toHaveBeenCalledOnce()
  expect(screen.getByLabelText('尚未生效的建议')).toHaveTextContent('用户提供的业务描述')
  expect(screen.queryByRole('button',{name:/批准/})).not.toBeInTheDocument()
})
