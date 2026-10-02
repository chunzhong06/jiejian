// 集合搜索共用外观与可访问名称；即时过滤或显式提交仍由所在页面负责。
import { SearchOutlined } from '@ant-design/icons'
import { Input, type InputProps } from 'antd'

export function SearchField({ className = '', ...props }: InputProps & { 'aria-label': string }) {
  return <Input allowClear {...props} prefix={<SearchOutlined aria-hidden/>} className={`product-search ${className}`}/>
}
