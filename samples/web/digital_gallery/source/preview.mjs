// 公开预览仅展示可公开的项目说明。
export function publicView(item) { return {title:item.data.title,summary:item.data.summary}; }
