import { Component, type ReactNode } from 'react';
import {subscribePageRefresh} from '../shared/lib/pageRefresh';
import { Notice } from "../shared/ui/feedback";
export class RouteBoundary extends Component<{
    children: ReactNode;
}, {
    failed: boolean;
}> {
    state = { failed: false };
    private unsubscribe?:()=>void;
    componentDidMount(){this.unsubscribe=subscribePageRefresh(()=>{if(this.state.failed)this.setState({failed:false})})}
    componentWillUnmount(){this.unsubscribe?.()}
    static getDerivedStateFromError() { return { failed: true }; }
    render() { return this.state.failed ? <Notice tone="negative">界面暂时未能打开，可通过右上角刷新重新尝试。</Notice> : this.props.children; }
}
