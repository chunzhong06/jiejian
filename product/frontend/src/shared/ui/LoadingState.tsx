// 等待提示与图标作为一个整体居中；页面和局部区域共用展示，不参与请求状态判断。
import { Spin } from 'antd'

export function LoadingState({ children, page = false }: { children: string; page?: boolean }) {
  return <div className={`loading-state${page ? ' loading-state--page' : ''}`} role="status" aria-live="polite" aria-busy="true">
    <span aria-hidden="true"><Spin /></span><span>{children}</span>
  </div>
}
