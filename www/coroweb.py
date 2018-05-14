import functools
import inspect
import logging
import os
import asyncio

from urllib import parse
from aiohttp import web
from apis import APIError


# ============================================   get，post装饰器   =====================================================
def get(path):
    # Define decorator @get('/path')
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'GET'
        wrapper.__route__ = path

        return wrapper

    return decorator


def post(path):
    # Define decorator @post('/path')
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'POST'
        wrapper.__route__ = path

        return wrapper

    return decorator


# ============================================   函数参数检查   ========================================================


# 函数fn是否有名字叫做request的参数，如果有，那么该参数必须在 *var(可变参数 var-position)前面使用
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == "request":  # 找到名为"request"的参数,置found为真
            found = True
            continue
        # VAR_POSITIONAL,表示可选参数,匹配*args
        # 若已经找到"request"关键字,但其不是函数的最后一个position-or-keyword参数,将报错
        # request参数必须是最后一个 position-or-keyword 参数
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and
                              param.kind != inspect.Parameter.KEYWORD_ONLY and
                              param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError(  # sig 代表fn函数的参数情况，在错误信息中将其打印出来
                "request parameter must be the last named parameter in function: %s%s" % (fn.__name__, str(sig)))
    return found


# 判断函数fn是否带有命名关键字参数
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # KEYWORD_ONLY, 表示命名关键字参数.
        # 因此下面的操作就是获得命名关键字参数名
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


# 判断函数fn是否带有关键字参数
def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # VAR_KEYWORD, 表示关键字参数, 匹配**kw
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


# 获取命名关键字参数名
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param, in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


# 获取默认值为空的，需要调用者传入值的命名关键字参数名
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param, in params.items():
        # 获取是命名关键字,且未指定默认值的参数名
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


# ============================================   封装路由函数   ========================================================
# 用来封装一个路由函数，使其能够自动解析request，
# 从request中取得路由函数需要的参数，存放在kw中，调用路由函数
class RequestHandler(object):
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request):
        kw = None

        # 第一步，把 KEYWORD-ONLY 和 VAR-KEYWORD 的参数从request中解析出来，存在kw中
        if self._required_kw_args or self._has_named_kw_args or self._has_var_kw_arg:

            # http method 为 post的处理
            if request.method == "POST":
                # http method 为post, 但request的content type为空, 返回丢失信息
                if not request.content_type:
                    return web.HTTPBadRequest("Missing Content-Type")
                ct = request.content_type.lower()  # 获得content type字段
                # 以下为检查post请求的content type字段
                # application/json表示消息主体是序列化后的json字符串
                if ct.startswith("application/json"):
                    params = await request.json()  # request.json方法的作用是读取request body, 并以json格式解码
                    if not isinstance(params, dict):  # 解码得到的参数不是字典类型, 返回提示信息
                        return web.HTTPBadRequest("JSON body must be object.")
                    kw = params  # post, content type字段指定的消息主体是json字符串,且解码得到参数为字典类型的,将其赋给变量kw
                # 以下2种content type都表示消息主体是表单
                elif ct.startswith("application/x-www-form-urlencoded") or ct.startswith("multipart/form-data"):
                    # request.post方法从request body读取POST参数,即表单信息,并包装成字典赋给kw变量
                    params = await request.post()
                    kw = dict(**params)
                else:
                    # 此处我们只处理以上三种post 提交数据方式
                    return web.HTTPBadRequest("Unsupported Content-Type: %s" % request.content_type)

            # http method 为 get的处理
            if request.method == "GET":
                # request.query_string表示url中的查询字符串
                # 比如"https://host/path?username=123&password=123",其中q=google就是query_string
                qs = request.query_string
                if qs:
                    kw = dict()  # 原来为None的kw变成字典
                    # parse_qs 返回字典，形式如下{'username': [123], 'password' = [123]}
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]

        # 第二步，这里解决positional-or-keyword参数，从request中取得需要的参数，存放在kw中

        # 若存在可变路由：/blog/{id}，若某个request.path = '/blog/{id}'
        # 则request.match_info返回{id = 123123123}
        if kw is None:
            kw = dict(**request.match_info)
        else:
            # kw 不为空,且requesthandler只存在命名关键字的,则只取命名关键字参数名放入kw
            if self._named_kw_args and not self._has_var_kw_arg:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # 遍历request.match_info, 若其key又存在于kw中,发出重复参数警告
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning("Duplicate arg name in named arg and kw args: %s" % k)
                # 把positional-or-keyword这个类型的 也存放在kw中
                kw[k] = v

        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)

        # 第三步，使用kw，调用路由函数
        logging.info('call with args: %s' % str(kw))
        try:
            return await self._func(**kw)
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


# ============================================   添加RequestHandler 实例   =============================================
# add_routes(app, 'handlers')

def add_static(app):
    # os.path.abspath(__file__), 返回当前脚本的绝对路径(包括文件名)
    # os.path.dirname(), 去掉文件名,返回目录路径
    # os.path.join(), 将分离的各部分组合成一个路径名
    # 因此以下操作就是将本文件同目录下的static目录(即www/static/)加入到应用的路由管理器中
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")  # pathlib.Path 是更适合人类使用的路径处理库
    app.router.add_static("/static/", path)
    logging.info("add static %s => %s" % ("/static/", path))


# 将处理函数注册到app上
# 处理将针对http method 和path进行
def add_route(app, fn):
    method = getattr(fn, "__method__", None)
    path = getattr(fn, "__route__", None)

    if path is None or method is None:
        raise ValueError("@get or @post not defined in %s." % str(fn))
    # 将非协程或生成器的函数变为一个协程.
    # 这句话好像没什么用呀
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info("add route %s %s => %s(%s)" %
                 (method, path, fn.__name__, '. '.join(inspect.signature(fn).parameters.keys())))
    # 注册request handler
    app.router.add_route(method, path, RequestHandler(app, fn))


# 自动注册所有请求处理函数
def add_routes(app, module_name):
    n = module_name.rfind(".")  # n 记录模块名中最后一个.的位置
    if n == (-1):  # -1 表示未找到,即module_name表示的模块直接导入
        # __import__()的作用同import语句,python官网说强烈不建议这么做
        # __import__(name, globals=None, locals=None, fromlist=(), level=0)
        # name -- 模块名
        # globals, locals -- determine how to interpret the name in package context
        # fromlist -- name表示的模块的子模块或对象名列表
        # level -- 绝对导入还是相对导入,默认值为0, 即使用绝对导入,正数值表示相对导入时,导入目录的父目录的层数

        # __import__ 作用同import语句，但__import__是一个函数，并且只接收字符串作为参数
        # __import__('os',globals(),locals(),['path','pip'], 0) ,等价于from os import path, pip
        mod = __import__(module_name, globals(), locals())
    else:  # 如果handler.py 位于一个包内，例如 'package.handler'
        name = module_name[n + 1:]  #
        # 以下语句表示, 先用__import__表达式导入模块以及子模块
        # 再通过getattr()方法取得子模块名, 如datetime.datetime
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    # 遍历模块目录
    for attr in dir(mod):
        # 忽略以_开头的属性与方法,_xx或__xx(前导1/2个下划线)指示方法或属性为私有的,__xx__指示为特殊变量
        # 私有的,能引用(python并不存在真正私有),但不应引用;特殊的,可以直接应用,但一般有特殊用途
        if attr.startswith("_"):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, "__method__", None)
            path = getattr(fn, "__route__", None)
            # 注册request handler, 与add.router.add_route(method, path, handler)一样的
            if method and path:
                add_route(app, fn)



