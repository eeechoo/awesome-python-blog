import asyncio
import logging

from aiohttp import web

import orm

logging.basicConfig(level=logging.INFO)


async def index(request):
    # 可以试下不要 content_type ，此时在浏览器中打开 index 页面，页面不会正常显示，而是出现一个download
    return web.Response(body='<h1>Hello, World</h1>'.encode(), content_type='text/html')


# 这个 coroutine 的主要任务是完成 server 的启动工作
async def init(loop):
    # 初始化 connection pool
    await orm.create_pool(loop=loop)
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/', index)
    server = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000')
    return server


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
# 这句话启动 server 监听请求的任务，并在 loop 中存在 coroutine 的情况下一直执行下去
# 直到键盘输入 CTRL + C 关闭线程
loop.run_forever()
