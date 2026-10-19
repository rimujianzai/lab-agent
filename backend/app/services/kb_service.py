import logging
from typing import cast
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Embeddable, EmbeddingFunction
from chromadb.utils import embedding_functions
import chromadb
from app.config import BASE_DIR

logger = logging.getLogger("lab_agent")

KB_DIR = BASE_DIR / "data" / "kb"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
# 知识库文档（data/kb/*.md）全是中文，必须用中文模型。
# 换成 -en- 那版英文模型检索中文文档不会报错，但召回质量会明显下降。
# 注意：换模型后 data/chroma 里用旧模型算出来的向量会失效（两个模型都是 512 维，
# chroma 不会报错，只会安静地返回不相关的结果），需要删掉该目录重新建库。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_collection = None
_embedding_fn: EmbeddingFunction[Embeddable] | None = None


def _build_embedding_fn(model_name: str) -> EmbeddingFunction[Embeddable]:
    """构造 embedding 函数，优先只用本地缓存，缓存里没有才联网下载。

    chromadb 的 SentenceTransformerEmbeddingFunction 只声明了处理纯文本，
    而 get_or_create_collection 期望的是能处理「文本 + 图片」的 EmbeddingFunction，
    两者的类型参数对不上。这里实际上只喂文本，所以用 cast 抹平差异。

    local_files_only 这个参数很关键：SentenceTransformer 默认会先去
    huggingface.co 核对一遍模型文件，失败还重试 5 次（1+2+4+8+16 秒）。
    国内网络访问 huggingface.co 基本都是直接超时（WinError 10060），
    于是整个启动就卡在这一步 —— 表现为 uvicorn 一直停在
    "Waiting for application startup."，端口不监听，前端所有请求都失败。
    指定只用本地缓存后不再联网，正常情况几秒就加载完。
    """
    factory = embedding_functions.SentenceTransformerEmbeddingFunction
    try:
        # 模型已经在本地缓存里（跑过一次就会缓存），这是正常路径
        return cast(
            "EmbeddingFunction[Embeddable]",
            factory(model_name=model_name, local_files_only=True),
        )
    except Exception:
        # 本地没有缓存（比如刚克隆项目、第一次跑），才回退到联网下载
        logger.warning("本地缓存里没有 %s，改为联网下载模型", model_name)
        return cast(
            "EmbeddingFunction[Embeddable]", factory(model_name=model_name)
        )


def get_embedding_fn() -> EmbeddingFunction[Embeddable]:
    """懒加载 embedding 模型：只加载一次，之后复用同一个实例"""
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn
    # SentenceTransformerEmbeddingFunction 自带类级缓存，同名模型也不会重复加载
    _embedding_fn = _build_embedding_fn(EMBEDDING_MODEL_NAME)
    return _embedding_fn


def warmup():
    """启动时预热：把模型加载 + 首次检索的开销付在启动阶段，别落在第一个用户请求上"""
    col = get_collcetion()
    if col.count() > 0:
        col.query(query_texts=["预热"], n_results=1)


def get_collcetion() -> Collection:
    """向量库的初始化"""

    global _collection
    if _collection is not None:
        return _collection
    KB_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(
        name="lab_kb", embedding_function=get_embedding_fn()
    )
    if col.count() == 0:
        ids = []
        docs = []
        metas = []
        for path in sorted(KB_DIR.glob("*.md")):
            text = path.read_text(encoding="UTF-8").strip()
            if not text:
                continue
            docs.append(text)
            ids.append(path.stem)
            metas.append({"source": path.name})
        if docs:
            col.add(ids=ids, documents=docs, metadatas=metas)
    _collection = col
    return col

def search(query: str):
    """根据关键字去检索向量库"""
    col = get_collcetion()
    if col.count() == 0:
        return ""
    limit = min(5, col.count())
    res = col.query(query_texts=[query], n_results=limit)
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]

    """
    以下是检索出来的资料：
    [预约规则.md]

    # 实验室预约规则...

    
    [安全规范.md]

    安全规范....
    """
    score_parts = []
    for doc, metas, dist in zip(docs, metas, distances):
        # 0-1 越接近1表示越相关
        score = 1 / (1 + dist)
        if score < 0.5:
            continue
        name = metas.get("source") or ""
        score_parts.append({"score": score, "content": f"[{name}]\n{doc}"})
    logger.debug("检索出来的 score_parts：%s", score_parts)
    score_parts.sort(key=lambda x: x["score"], reverse=True)
    final_parts = [item["content"] for item in score_parts[:2]]
    return "\n\n".join(final_parts)
