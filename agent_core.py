from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
import docker
import os
from dotenv import load_dotenv
from rag_store import search_fault_kb
from db import add_audit_log

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# 连接本地Docker引擎
client = docker.from_env()

# ========= 命令白名单：只允许下面这些只读命令 =========
ALLOW_CMD = {"ps", "df -h", "ls", "cat", "dmesg", "ss -tlnp", "netstat -tlnp"}

# 全局向量库
vec_db = None
user_global_query = ""

# 工具1：列出所有运行中的容器
@tool
def list_running_containers(ignored: str = "") -> str:
    """
    列出宿主机上正在运行的docker容器，返回容器名称和容器ID。
    当不知道有哪些容器、不确定容器名字的时候调用此工具。
    参数 ignored：无实际用途，忽略即可。
    """
    global user_global_query
    containers = client.containers.list()
    res = []
    for c in containers:
        res.append(f"容器ID:{c.short_id}, 容器名:{c.name}, 状态:{c.status}")
    result_str = "\n".join(res)
    add_audit_log(user_global_query, "all", "list", result_str[:1500])
    return result_str

# 工具2：在指定容器内部执行命令（带白名单校验）
@tool
def exec_container_cmd(params: str) -> str:
    """
    在指定容器内部执行linux查询命令。参数格式："容器名|命令"，例如：mysql|df -h；也可以传JSON格式 {"container_name": "mysql", "cmd": "df -h"}
    """
    global user_global_query
    import json
    container_name = params.strip()
    cmd = ""
    # 兼容 JSON 格式
    try:
        data = json.loads(container_name)
        if isinstance(data, dict):
            container_name = str(data.get("container_name", container_name))
            cmd = str(data.get("cmd", "")).strip()
    except Exception:
        pass
    # 兼容 "容器名|命令" 格式
    if not cmd and "|" in container_name:
        parts = container_name.split("|", 1)
        container_name = parts[0].strip()
        cmd = parts[1].strip()
    if not cmd:
        return "参数格式错误：请使用 容器名|命令 格式，例如 mysql|df -h"
    if cmd not in ALLOW_CMD:
        return f"【禁止执行】命令 {cmd} 不在白名单，不允许执行！仅允许：{ALLOW_CMD}"
    try:
        container = client.containers.get(container_name)
        exit_code, output = container.exec_run(cmd)
        output_str = output.decode("utf-8", errors="ignore")
        add_audit_log(user_global_query, container_name, cmd, output_str[:1500])
        return f"执行命令 {cmd} 结果：\n{output_str}"
    except Exception as e:
        err_msg = f"执行失败：{str(e)}"
        add_audit_log(user_global_query, container_name, cmd, err_msg)
        return err_msg

# 工具3：获取容器日志
@tool
def get_container_log(params: str) -> str:
    """
    获取容器最近的日志，用于排查容器报错、崩溃问题。
    参数格式：容器名|日志行数，例如：nginx|30；也可以传JSON格式 {"container_name": "nginx", "lines": 30}
    """
    global user_global_query
    import json
    container_name = params.strip()
    lines = 20
    # 兼容 JSON 格式
    try:
        data = json.loads(container_name)
        if isinstance(data, dict):
            container_name = str(data.get("container_name", container_name))
            if isinstance(data.get("lines"), int):
                lines = data["lines"]
    except Exception:
        pass
    # 兼容 "容器名|行数" 格式
    if "|" in container_name:
        parts = container_name.split("|")
        container_name = parts[0].strip()
        if len(parts) > 1 and parts[1].strip().isdigit():
            lines = int(parts[1].strip())
    try:
        container = client.containers.get(container_name)
        log_bytes = container.logs(tail=lines).decode("utf-8", errors="ignore")
        add_audit_log(user_global_query, container_name, "logs", log_bytes[:1500])
        return f"容器{container_name}最近{lines}行日志:\n{log_bytes}"
    except Exception as e:
        err_msg = f"获取日志失败: {str(e)}"
        add_audit_log(user_global_query, container_name, "logs", err_msg)
        return err_msg

# 工具4：检索Docker故障知识库
@tool
def search_docker_fault_kb(query: str) -> str:
    """
    检索Docker故障知识库，查询同类故障排查方案。
    参数query：故障描述，例如：容器反复崩溃
    """
    global vec_db, user_global_query
    result = search_fault_kb(vec_db, query)
    add_audit_log(user_global_query, "knowledge", "search", result[:1500])
    return result
tools = [list_running_containers, exec_container_cmd, get_container_log, search_docker_fault_kb]

# Agent提示词
prompt = PromptTemplate.from_template("""
你是Docker容器故障诊断Agent，使用ReAct框架。
你的工作流程：
1. 根据用户的故障描述，思考需要收集哪些信息；
2. 按需调用工具：列出容器、进入容器执行白名单命令、拉取容器日志、检索故障知识库；
3. 综合命令返回结果+知识库内容，分析故障根因，给出排查结论；
4. 不要编造容器信息，如果工具返回为空，如实告知。

调用工具注意：
- exec_container_cmd 参数必须用 容器名|命令 格式，例如 mysql|df -h
- get_container_log 参数用 容器名|行数 格式，例如 nginx|30
- 只能使用白名单内只读命令，禁止任何删除、停止、重启操作。

工具列表：
{tools}
工具名称：
{tool_names}

用户故障描述：{input}
思考过程：{agent_scratchpad}
""")

llm = ChatOpenAI(
    model="qwen-turbo",
    openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
    openai_api_base="https://ws-vf1ymytkmznbajkq.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)

agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)

def run_agent(fault_query, vector_db):
    global vec_db, user_global_query
    vec_db = vector_db
    user_global_query = fault_query
    result = agent_executor.invoke({"input": fault_query})
    return result["output"]

