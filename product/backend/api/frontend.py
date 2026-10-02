# 静态HTML每次重新校验，带内容散列的资源长期缓存；不影响API与MCP的授权边界。
import re

from fastapi.staticfiles import StaticFiles


class ProductStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # StaticFiles已把路由转换成平台路径；缓存规则仍按URL分隔符匹配。
        path = path.replace('\\', '/')
        if path in {'.', '', 'index.html', 'frontend-manifest.json'} or path.endswith('.html'):
            response.headers['Cache-Control'] = 'no-cache'
        elif re.fullmatch(r'assets/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+', path):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response
