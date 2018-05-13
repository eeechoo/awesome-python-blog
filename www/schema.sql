drop database if exists awesome;

create database awesome;

use awesome;

# 将权限授予哪个用户。格式：”用户名”@”登录IP或域名”
# identified by：指定用户的登录密码
grant select, insert, update, delete on awesome.* to 'www-data'@'localhost' identified by 'www-data';

# INDEX 与 KEY 的区别：
# MySQL中的约束效果是通过索引来实现的，MySQL数据库判断是否当前列是否unique就是通过unique索引判断的。
# 在理论上是不能将MySQL的key和index划等号的，他们不是一回事，但在实际使用中，他们基本没有区别。
# https://segmentfault.com/q/1010000005766771/a-1020000005767098
create table users (
    `id` varchar(50) not null,
    `email` varchar(50) not null,
    `passwd` varchar(50) not null,
    `admin` bool not null,
    `name` varchar(50) not null,
    `image` varchar(500) not null,
    `created_at` real not null,
    unique key `idx_email` (`email`),
    key `idx_created_at` (`created_at`),
    primary key (`id`)
) engine=innodb default charset=utf8;

create table blogs (
    `id` varchar(50) not null,
    `user_id` varchar(50) not null,
    `user_name` varchar(50) not null,
    `user_image` varchar(500) not null,
    `name` varchar(50) not null,
    `summary` varchar(200) not null,
    `content` mediumtext not null,
    `created_at` real not null,
    key `idx_created_at` (`created_at`),
    primary key (`id`)
) engine=innodb default charset=utf8;

create table comments (
    `id` varchar(50) not null,
    `blog_id` varchar(50) not null,
    `user_id` varchar(50) not null,
    `user_name` varchar(50) not null,
    `user_image` varchar(500) not null,
    `content` mediumtext not null,
    `created_at` real not null,
    key `idx_created_at` (`created_at`),
    primary key (`id`)
) engine=innodb default charset=utf8;