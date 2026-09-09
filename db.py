# -*- coding: utf-8 -*-
# @Time: 2026/9/9 14:10
# @Author: wanglu
# @Email: 1837935123@qq.com
# @File: db.py

import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("audit.db")
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_query TEXT,
        container_name TEXT,
        exec_cmd TEXT,
        cmd_result TEXT,
        create_time TEXT
    )
    ''')
    conn.commit()
    conn.close()

def add_audit_log(user_query, container_name, exec_cmd, cmd_result):
    conn = sqlite3.connect("audit.db")
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO audit_log(user_query, container_name, exec_cmd, cmd_result, create_time)
    VALUES (?,?,?,?,?)
    ''', (user_query, container_name, exec_cmd, cmd_result, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_all_log():
    conn = sqlite3.connect("audit.db")
    cur = conn.cursor()
    res = cur.execute("SELECT * FROM audit_log")
    return res.fetchall()

if __name__ == "__main__":
    init_db()
    print("审计数据库初始化完成")