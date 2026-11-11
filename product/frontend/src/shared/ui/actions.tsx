import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from 'react';
import LoadingOutlined from '@ant-design/icons/LoadingOutlined';
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import { Hint } from "./Hint";
import {useWorkflow} from '../lib/workflow';
import {go} from '../lib/navigation';
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
    kind?: 'default' | 'primary' | 'quiet' | 'danger';
    busy?: boolean;
    busyLabel?: string;
    complete?: boolean;
    size?: 'regular' | 'compact';
    icon?: ReactNode;
    tip?: string;
}>(function Button({ children, kind = 'default', busy = false, busyLabel, complete = false, size = 'regular', icon, tip, title, ...props }, ref) {
    const label = tip ?? title ?? (!children ? props['aria-label'] : undefined);
    // 忙碌指示覆盖原内容，保留原图标和文字占位，提交时不能挤动相邻操作。
    const button = <button {...props} ref={ref} type={props.type ?? 'button'} className={`jj-button is-${kind} ${props.className ?? ''}`} data-size={size} data-icon-only={!children || undefined} data-complete={complete || undefined} disabled={props.disabled || busy} aria-busy={busy || undefined}>{complete ? <CheckOutlined className="jj-button-complete" aria-hidden="true"/> : icon}{children}{busy && <span className="jj-button-progress" aria-hidden="true"><LoadingOutlined spin/>{busyLabel&&<span>{busyLabel}</span>}</span>}</button>;
    // 提示停用只改变浮层状态，不能在忙碌切换时替换按钮 DOM。
    return label ? <Hint label={label} disabled={props.disabled || busy}>{button}</Hint> : button;
});
export function ActionLink({ kind = 'quiet', presentation = 'inline', navigationScope = 'workflow', className = '', onClick, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & {
    kind?: 'default' | 'primary' | 'quiet';
    presentation?: 'inline' | 'row';
    /** 原有整页跳转不因改用链接而被嵌入工作流接管。 */
    navigationScope?: 'workflow' | 'page';
}) {
    // 链接沿用同一色彩和反馈；普通阅读导航不占用提交按钮的几何与视觉重量。
    const workflow=useWorkflow();
    return <a {...props} onClick={event=>{onClick?.(event);if(!event.defaultPrevented&&(!props.target||props.target==='_self')&&!props.download&&event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&props.href?.startsWith('#/')&&(navigationScope==='page'||workflow)){event.preventDefault();if(navigationScope==='page')go(props.href.slice(1));else workflow!.open(props.href.slice(1));}}} data-navigation={kind === 'quiet' ? presentation : undefined} className={`jj-button is-${kind} ${className}`}/>;
}
