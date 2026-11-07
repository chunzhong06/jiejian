"""独占 loopback 临时数据库；只在显式 L4 使用，不注册系统服务或读取用户业务库。"""
from contextlib import contextmanager
from pathlib import Path
import os
import secrets
import socket
import subprocess
import time
from types import SimpleNamespace
import pytest


@contextmanager
def local_database(engine,root):
    repository=Path(__file__).resolve().parents[4]
    with ascii_database_paths(repository,engine,root) as (repository,root):
        with _local_database(engine,root,repository) as value:yield value


@contextmanager
def ascii_database_paths(repository,engine,root):
    """MySQL Windows 启动器截断本机中文参数；临时盘符仍指向原 var，退出撤销。"""
    if os.name!='nt' or engine!='MYSQL' or str(repository).isascii():
        yield repository,root;return
    import ctypes
    mask=ctypes.windll.kernel32.GetLogicalDrives()
    drive=next((chr(number+65)+':' for number in range(25,3,-1) if not mask&(1<<number)),None)
    if drive is None:raise RuntimeError('没有可用的临时数据库盘符')
    subprocess.run(['subst',drive,str(repository)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:yield Path(drive+'/'),Path(drive+'/')/root.resolve().relative_to(repository)
    finally:subprocess.run(['subst',drive,'/D'],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


@contextmanager
def _local_database(engine,root,repository):
    cache=repository/'var/cache/database-test-distributions'
    base=Path(os.environ.get('JIEJIAN_TEST_'+engine+'_BIN',str(cache/('postgresql-18.6-5/pgsql/bin' if engine=='POSTGRESQL' else 'mysql-8.4.13-winx64/bin'))))
    binary=base/('postgres.exe' if engine=='POSTGRESQL' else 'mysqld.exe')
    if not binary.is_file():pytest.skip('需要显式配置本机测试数据库二进制目录')
    root.mkdir(parents=True)
    data=root/'data'
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    run=lambda args:subprocess.run([str(value) for value in args],check=True,stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=45)
    if engine=='POSTGRESQL':
        run([base/'initdb.exe','-D',data,'-U','jiejian','--auth=trust','--no-locale','--encoding=UTF8'])
        args=[binary,'-D',data,'-h','127.0.0.1','-p',port,'-c','logging_collector=off']
    else:
        run([binary,'--no-defaults','--initialize-insecure','--basedir='+str(base.parent),'--datadir='+str(data)])
        args=[binary,'--no-defaults','--console','--basedir='+str(base.parent),'--datadir='+str(data),'--bind-address=127.0.0.1',
            '--port='+str(port),'--mysqlx=OFF','--skip-log-bin']
    log=(root/'server.log').open('wb')
    process=subprocess.Popen([str(value) for value in args],stdin=subprocess.DEVNULL,stdout=log,
        stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    password=secrets.token_urlsafe(24)
    def connect():
        if engine=='POSTGRESQL':
            import psycopg
            return psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='jiejian',password=password,connect_timeout=1)
        import pymysql
        return pymysql.connect(host='127.0.0.1',port=port,user='root',password='',connect_timeout=1)
    try:
        deadline=time.monotonic()+20
        while True:
            try:database=connect();break
            except Exception:
                if time.monotonic()>=deadline or process.poll() is not None:
                    log.flush()
                    raise RuntimeError('临时数据库未就绪：'+(root/'server.log').read_text(errors='replace')[-2400:]) from None
                time.sleep(.1)
        if engine=='MYSQL':
            with database.cursor() as cursor:
                cursor.execute('CREATE DATABASE jiejian_test')
                cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",(password,))
            database.commit()
        database.close()
        yield SimpleNamespace(engine=engine,port=port,password=password,database='postgres' if engine=='POSTGRESQL' else 'jiejian_test',
            namespace='public' if engine=='POSTGRESQL' else 'jiejian_test',username='jiejian' if engine=='POSTGRESQL' else 'root')
    finally:
        if process.poll() is None:
            if engine=='POSTGRESQL':
                run([base/'pg_ctl.exe','stop','-D',data,'-m','fast','-w','-t','10'])
            else:
                import pymysql
                shutdown=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,connect_timeout=2)
                try:
                    with shutdown.cursor() as cursor:cursor.execute('SHUTDOWN')
                finally:shutdown.close()
            process.wait(10)
        log.close()
