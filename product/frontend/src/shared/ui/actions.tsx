import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { LoadingOutlined } from '@ant-design/icons';
import { Hint } from "./Hint";
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
    kind?: 'default' | 'primary' | 'quiet' | 'danger';
    busy?: boolean;
    icon?: ReactNode;
    tip?: string;
}>(function Button({ children, kind = 'default', busy = false, icon, tip, title, ...props }, ref) {
    const label = tip ?? title ?? (!children ? props['aria-label'] : undefined);
    const button = <button {...props} ref={ref} type={props.type ?? 'button'} className={`jj-button is-${kind} ${props.className ?? ''}`} disabled={props.disabled || busy} aria-busy={busy || undefined}>{busy ? <LoadingOutlined aria-hidden="true" spin/> : icon}{children}</button>;
    return label && !props.disabled && !busy ? <Hint label={label}>{button}</Hint> : button;
});
export function ActionLink({ kind = 'quiet', className = '', ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & {
    kind?: 'default' | 'primary' | 'quiet';
}) { return <a {...props} className={`jj-button is-${kind} ${className}`}/>; }
