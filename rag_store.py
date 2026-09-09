import os
import requests
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_URL = "https://ws-vf1ymytkmznbajkq.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

class BAILEIANEmbeddings(Embeddings):
    """百炼专属域名 embedding 封装（input 使用 contents 结构）"""
    def __init__(self, api_key, base_url, model="text-embedding-v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def _post(self, texts):
        resp = requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"embedding 调用失败: {resp.status_code} {resp.text}")
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    def embed_documents(self, texts):
        return self._post(texts)

    def embed_query(self, text):
        return self._post([text])[0]

def load_knowledge():
    with open("knowledge/docker_fault.txt", "r", encoding="utf-8") as f:
        text = f.read()
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=30)
    chunks = splitter.split_text(text)
    embeddings = BAILEIANEmbeddings(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=BASE_URL
    )
    vec_db = Chroma.from_texts(chunks, embeddings, persist_directory="./chroma_db")
    vec_db.persist()
    return vec_db

def search_fault_kb(vec_db, query, top_k=2):
    docs = vec_db.similarity_search(query, k=top_k)
    return "\n".join([doc.page_content for doc in docs])

if __name__ == "__main__":
    vdb = load_knowledge()
    print("Docker故障知识库加载完成")
    res = search_fault_kb(vdb, "容器反复崩溃")
    print("检索结果：", res)

