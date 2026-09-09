# -*- coding: utf-8 -*-
# @Time: 2026/9/9 14:09
# @Author: wanglu
# @Email: 1837935123@qq.com
# @File: main.py
from fastapi import FastAPI
from pydantic import BaseModel
from db import init_db, get_all_log
from rag_store import load_knowledge
from agent_core import run_agent

app = FastAPI(title="Docker容器故障诊断Agent")
vec_db = None

@app.on_event("startup")
async def startup():
    global vec_db
    init_db()
    vec_db = load_knowledge()
    print("系统启动成功，RAG知识库、审计数据库加载完成")

class FaultReq(BaseModel):
    query: str

@app.post("/agent/analyze")
async def analyze_fault(req: FaultReq):
    resp = run_agent(req.query, vec_db)
    return {"diagnose_result": resp}

@app.get("/audit/logs")
async def get_audit():
    return {"audit_logs": get_all_log()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)