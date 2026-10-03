// 展示已形成的操作回执及回读入口，不重放写操作。
import { Button } from 'antd'

export function TaskReceipt({ message, pending, onRetry }: { message: string; pending?: string; onRetry?: () => void }) {
  return <div className="task-receipt" data-pending={Boolean(pending)} role="status">
    <div><strong>{message}</strong>{pending && <p>{pending}</p>}</div>
    {onRetry && <Button onClick={onRetry}>重新读取下一步</Button>}
  </div>
}
