import logging

import aiomysql


# ============================================   aiomysql pool   =======================================================
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['database'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


async def destory_pool():
    global __pool
    if __pool is not None:
        __pool.close()
        await __pool.wait_closed()


# ============================================   Basic Sql  处理函数   =================================================
# 接收 select 类型 sql 语句，语句中的参数使用 '?' 作为占位符
# >>> cursor.execute('insert into `user` (`id`, `name`) values (?, ?)', ['1', 'Michael'])
# sql 语句中使用反引号包裹用户用户定义的 属性，这样用户定义属性的时候占用了一些sql 语句关键字也不会报错
async def select(sql, args, size=None):
    logging.info('SELECT SQL: %s ---> %s' % (sql, args))
    # 这句话我写成 async with __pool as conn:就会在models_test中出现错误,所以有必要研究下这里的语法
    with (await __pool) as conn:
        # 这里的 cursor 也是相当于一个 context manager，不知道能不能使用 with as 结构。
        cur = await conn.cursor(aiomysql.DictCursor)
        await cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        await cur.close()
        logging.info('SELECT SQL %s rows returned' % len(rs))
        return rs


# 参数含义与 select 函数相同，
# autocommit 参数设置为 True 代表每执行一条 DML sql 语句都提交
# autocommit 参数设置为 False 代表多条 DML sql 语句才会 commit or rollback，
# autocommit = False 时需要显示的调用 conn.begin() 来关闭 autocommit
async def execute(sql, args, autocommit=True):
    logging.info('DML SQL: %s ---> %s' % (sql, args))
    with (await __pool) as conn:
        if not autocommit:
            await conn.begin()
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            affected = cur.rowcount
            await cur.close()
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            print(e)
            if not autocommit:
                await conn.rollback()
            raise e
        logging.info('DML SQL %s rows affected' % affected)
        return affected


# ============================================   ModelMetaclass   ======================================================

'''
class User(Model):
    __table__ = 'users'

    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
对于这样的类，希望执行完这三条语句后去执行 ModelMetaclass 去动态的改变类
'''


def create_args_string(num):
    temp = []
    for n in range(num):
        temp.append('?')
    return ', '.join(temp)


class ModelMetaclass(type):
    # mcs 是 metaclass的缩写，代表metaclass类本身
    def __new__(mcs, name, bases, attr):
        # 如果是 名字叫做 Model 的类传入，那么就不修改这个类，直接交给 type 去产生这个类即可
        if name == 'Model':
            return type.__new__(mcs, name, bases, attr)
        # 如果是 名字叫做 User 等这样继承自Model的用户定义的类传入，就需要修改这个类，然后交给 type 去产生这个类
        tableName = attr.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))

        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attr.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                # 找到主键
                if v.primary_key:
                    # 已经存在主键
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attr.pop(k)

        # 现在 mapping 中存在{   'email': StringField(ddl='varchar(50)')
        #                        'passwd': StringField(ddl='varchar(50)')} 这样的映射关系
        # fields 中保存 ['email', 'passwd']
        attr['__mappings__'] = mappings  # 保存属性和列的映射关系
        attr['__table__'] = tableName
        attr['__primary_key__'] = primaryKey  # 主键属性名
        attr['__fields__'] = fields  # 除主键外的属性名
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attr['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attr['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (
            tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attr['__update__'] = 'update `%s` set %s where `%s`=?' % (
            tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attr['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(mcs, name, bases, attr)


# ============================================   由 ModelMetaclass 作为元类创建的 Model   ==============================
'''
u = User(id=12345, name='Michael', email='test@orm.org', password='my-pwd')
'''


class Model(dict, metaclass=ModelMetaclass):
    # --------------------------------------------   和 dict 本身相关的属性   -------------------------------------------
    # 继承自 dict， 所以Model也可以像字典一样初始化
    def __init__(self, **kw):
        super().__init__(**kw)

    # 实现支持类似u.name的使用方式
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    # 使用接口函数取得属性值，如果对应 key 不存在，也就是说 __getattr__ 中 raise AttributeError，
    # getattr 会捕捉到这个异常并返回None
    # 使用u.getValue('created_at') 会返回None
    def getValue(self, key):
        return getattr(self, key, None)

    # 使用u.getValueOrDefault('created_at') 第一次访问该属性的时候会生成一个有效值，并将其写入dict中
    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            # 对于例如 created_at = FloatField(default=time.time)
            #          id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
            # 这种情况 default 是callable
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    # --------------------------------------------   调用select 和 execute   -------------------------------------------
    @classmethod
    async def find(cls, pk):
        # find object by primary key
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        # size = 1， 执行 fetchmany，返回一个list，list每个元素都是字典
        # 所以rs[0] 是字典，类似于 {'id': 12, 'name': Michael}
        # 使用cls(** rs[0]) 构建出来一个user instance
        return cls(**rs[0])

    # 为了执行例如 User.findNumber('count(id)')
    # Blog.findNumber('count(id)')
    #  Comment.findNumber('count(id)')
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        # find number by select and where
        # 这里的 _num_ 为别名, 相当于 sql = ['select %s as `_num_` from `%s`' % (selectField, cls.__table__)]
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        # rs 代表 rows
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        # 所以rs[0] 是字典，类似于 {'_num_': ***}
        return rs[0]['_num_']

    # 为了执行例如User.findAll(where='gender=? AND age>?', args=[F, 24,], orderBy='age DESC' limit=(5,2))
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        # find objects by where clause
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)  # list extend method
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    # self.__insert = 'insert into `tableName` (escapedFields, `primaryKey`) values (?, ?, ?)'
    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    # 只有经过了u.save 执行 u.update和u.remove才有意义，这也就是为什么u.save中采用getValueOrDefault
    # self.__update__ = 'update `tableName` set `field`=? `field`=?, where `primaryKey`=?'
    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    # self.__delete__ = 'delete from `tableName` where `primaryKey`=?'
    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)


# ============================================   各类 Field   ==========================================================
# 默认各个 Field 的 primary key 均为 False，
# column_type 对应 varchar(100), boolean, bigint， real, text等
# default     对应 None，        False，  0，      0.0,  None
# name 一般不指定，就使用默认的None值
class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    # Field一个实例代表表中的一列，所以有表一列的各种属性
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)
