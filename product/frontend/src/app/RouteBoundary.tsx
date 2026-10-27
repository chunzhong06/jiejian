import { Component, type ReactNode } from 'react';
import { Button } from "../shared/ui/actions";
import { Notice } from "../shared/ui/feedback";
export class RouteBoundary extends Component<{
    children: ReactNode;
}, {
    failed: boolean;
}> {
    state = { failed: false };
    static getDerivedStateFromError() { return { failed: true }; }
    render() { return this.state.failed ? <Notice>界面暂时未能打开。<Button onClick={() => location.reload()}>重新打开界面</Button></Notice> : this.props.children; }
}
