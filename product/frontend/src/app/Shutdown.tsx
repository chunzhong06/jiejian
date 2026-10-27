import { useRef, useState } from 'react';
import { PoweroffOutlined } from '@ant-design/icons';
import { systemApi } from '../entities/runtime/api/system';
import { Button } from "../shared/ui/actions";
import { Dialog } from "../shared/ui/Dialog";
import { ErrorNote, Notice } from "../shared/ui/feedback";
export function Shutdown() {
    const [open, setOpen] = useState(false);
    const [state, setState] = useState<'idle' | 'sending' | 'accepted' | 'unknown'>('idle');
    const [error, setError] = useState<unknown>();
    const pending = useRef(false);
    const quit = async () => {
        if (pending.current)
            return;
        pending.current = true;
        setState('sending');
        try {
            await systemApi.shutdown();
            setState('accepted');
        }
        catch (value) {
            // 连接断开时服务可能已接收退出请求，保留入口状态，不自动重发。
            setError(value);
            setState('unknown');
        }
    };
    return <>
    <Button kind="quiet" className="jj-nav-item" icon={<PoweroffOutlined aria-hidden="true"/>} onClick={() => setOpen(true)}>退出界鉴</Button>
    {open && <Dialog title={state === 'accepted' ? '正在退出界鉴' : '退出界鉴？'} onClose={() => setOpen(false)} actions={state === 'idle' ? dismiss => <>
      <Button onClick={dismiss}>继续使用</Button>
      <Button kind="danger" onClick={() => void quit()}>退出界鉴</Button>
    </> : undefined}>
      {state === 'idle' && <p>退出将停止当前检查并关闭本地服务。已保存的规则、材料和报告会保留。</p>}
      {state === 'sending' && <Notice>正在请求退出。</Notice>}
      {state === 'accepted' && <Notice>退出请求已接收，服务正在清理当前任务。</Notice>}
      {state === 'unknown' && <><ErrorNote error={error}/><p>退出结果尚未确认，请查看启动窗口中的服务状态。</p></>}
    </Dialog>}
  </>;
}
