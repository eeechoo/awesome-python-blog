import asyncio
import logging
import orm
import sys
from models import User

import mysql.connector

logging.basicConfig(level=logging.INFO)


async def test(loop):
    await orm.create_pool(loop=loop, user='www-data', password='www-data', database='awesome')

    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
    await u.save()
    print(u)

    u.name = 'Michael'
    await u.update()
    print(u)

    print(u.id)
    r = await User.find(u.id)
    print(r)

    r = await User.findNumber('name', where='passwd=?', args=['1234567890'])
    print(r)

    r = await User.findAll(where='passwd=?', args=['1234567890'])
    print(r)

    await u.remove()

    await orm.destory_pool()


loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
loop.close()
# if loop.is_closed():
#     sys.exit(0)

# sql check code
# conn = mysql.connector.connect(user='www-data', password='www-data', database='awesome')
# cursor = conn.cursor()
# cursor.execute('select * from users')
# data = cursor.fetchall()
# print(data)
