# 静态HTML每次重新校验，带内容散列的资源长期缓存；不影响API与MCP的授权边界。
import re
import mimetypes

from fastapi.staticfiles import StaticFiles


class ProductStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        # StaticFiles已把路由转换成平台路径；缓存规则仍按URL分隔符匹配。
        path = path.replace('\\', '/')
        asset = re.fullmatch(r'assets/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+', path)
        headers = {key.lower():value for key,value in scope['headers']}
        encodings = {}
        for entry in headers.get(b'accept-encoding', b'').decode('latin-1').split(','):
            name, *parameters = entry.strip().lower().split(';')
            quality = next((part.strip()[2:] for part in parameters if part.strip().startswith('q=')), '1')
            try:encodings[name] = float(quality)
            except ValueError:encodings[name] = 0
        compressed = bool(asset and b'range' not in headers and encodings.get('gzip', encodings.get('*', 0)) > 0
            and self.lookup_path(path+'.gz')[1] is not None)
        response = await super().get_response(path+'.gz' if compressed else path, scope)
        if asset:
            response.headers['Vary'] = 'Accept-Encoding'
        if compressed:
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Type'] = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if path in {'.', '', 'index.html', 'frontend-manifest.json'} or path.endswith('.html'):
            response.headers['Cache-Control'] = 'no-cache'
        elif asset:
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response
