import asyncio
import datetime
import logging
import orm
import time
import os

from aiohttp import web
from jinja2 import Environment, FileSystemLoader
from coroweb import add_static, add_routes
from middlewares import logger_factory, data_factory, response_factory

logging.basicConfig(level=logging.INFO)

def datetime_filter(t):
    # 定义时间差
    delta = int(time.time()-t)
    # 针对时间分类
    if delta < 60:
        return u"1分钟前"
    if delta < 3600:
        return u"%s分钟前" % (delta // 60)
    # 86400 秒，是24小时
    if delta < 86400:
        return u"%s小时前" % (delta // 3600)
    if delta < 604800:
        return u"%s天前" % (delta // 86400)
    # 超过 604800 秒，也就是7天前
    dt = datetime.fromtimestamp(t)
    return u"%s年%s月%s日" % (dt.year, dt.month, dt.day)

# 选择jinja2作为模板, 初始化模板
def init_jinja2(app, **kw):
    logging.info("init jinja2...")
    options = dict(
        autoescape=kw.get("autoescape", True),  # 自动转义xml/html的特殊字符
        block_start_string=kw.get("block_start_string", "{%"),  # 代码块开始标志
        block_end_string=kw.get("block_end_string", "%}"),  # 代码块结束标志
        variable_start_string=kw.get("variable_start_string", "{{"),  # 变量开始标志
        variable_end_string=kw.get("variable_end_string", "}}"),  # 变量结束标志
        auto_reload=kw.get("auto_reload", True)  # 每当对模板发起请求,加载器首先检查模板是否发生改变.若是,则重载模板
    )
    path = kw.get("path", None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    logging.info("set jinja2 template path: %s" % path)
    # 初始化jinja2环境, options参数,之前已经进行过设置
    # 加载器负责从指定位置加载模板, 此处选择FileSystemLoader,顾名思义就是从文件系统加载模板,前面我们已经设置了path
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get("filters", None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    # 将jinja环境赋给app的__templating__属性
    app["__templating__"] = env


# 这个 coroutine 的主要任务是完成 server 的启动工作
async def init(loop):
    # 初始化 connection pool
    await orm.create_pool(loop=loop, host='127.0.0.1', port=3306, user='www-data', password='www-data', database='awesome')

    # 创建web应用,
    app = web.Application(loop=loop,
                          middlewares=[logger_factory, data_factory, response_factory])

    init_jinja2(app, filters=dict(datetime=datetime_filter))

    add_static(app)
    add_routes(app, "handlers")

    server = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000')
    return server


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
# 这句话启动 server 监听请求的任务，并在 loop 中存在 coroutine 的情况下一直执行下去
# 直到键盘输入 CTRL + C 关闭线程
loop.run_forever()
