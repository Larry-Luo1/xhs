"""数据库模型与操作 - 基于 SQLAlchemy (SQLite)"""
from __future__ import annotations

import datetime
from datetime import timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Account(Base):
    """小红书账号信息"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(64), unique=True, nullable=False, comment="账号标识")
    username = Column(String(128), nullable=True, comment="账号用户名/手机号")
    cookie = Column(Text, nullable=True, comment="完整Cookie字符串")
    user_id = Column(String(64), nullable=True, comment="小红书uid")
    status = Column(
        String(32), nullable=False, default="active",
        comment="active | rate_limited | banned | invalid"
    )
    request_count = Column(Integer, default=0, comment="累计请求次数")
    cookie_updated_at = Column(DateTime, nullable=True, comment="Cookie最近更新时间")
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))


class Proxy(Base):
    """代理IP信息"""
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host = Column(String(128), nullable=False)
    port = Column(Integer, nullable=False)
    protocol = Column(String(16), default="http", comment="http | socks5")
    username = Column(String(128), nullable=True)
    password = Column(String(128), nullable=True)
    bound_account_id = Column(String(64), nullable=True, comment="绑定的账号ID")
    is_valid = Column(Boolean, default=True)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))


class Task(Base):
    """采集任务"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(String(64), nullable=False, comment="帖子ID")
    note_url = Column(Text, nullable=True, comment="帖子原始链接")
    status = Column(
        String(32), default="pending",
        comment="pending | running | done | failed"
    )
    total_comments = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))


class CommentUser(Base):
    """采集到的评论用户"""
    __tablename__ = "comment_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False, comment="小红书用户ID")
    nickname = Column(String(256), nullable=True)
    comment_count = Column(Integer, default=1, comment="该用户在本帖的评论数")
    ip_location = Column(String(64), nullable=True, comment="IP属地")
    collected_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("note_id", "user_id", name="uq_note_user"),
    )


# ---------- 引擎 & Session 工厂 ----------

_engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """初始化数据库（建表）"""
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """返回一个新的数据库会话，调用方负责关闭"""
    return SessionLocal()
