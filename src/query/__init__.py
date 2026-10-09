"""
RAG问答模块 (RAG Query)

负责接收用户查询，从向量数据库检索相关内容，并调用 LLM 生成回答。

主要组件：
- Retriever: 检索器，从向量数据库检索相关文档块
- LLMClient: LLM客户端，支持多种LLM提供商
- QAEngine: 问答引擎，整合检索和生成
- RAGQueryService: 统一的问答服务

输入数据结构：
- QueryInput: 查询输入
- RetrievalConfig: 检索配置
- LLMConfig: LLM配置

输出数据结构：
- RetrievedChunk: 检索到的文档块
- SourceReference: 来源引用
- QueryResponse: 查询响应

使用示例：
    from src.query import RAGQueryService
    from src.models import QueryInput, LLMConfig
    
    service = RAGQueryService()
    response = service.query(
        QueryInput(
            query="这篇论文的主要贡献是什么？",
            llm_config=LLMConfig(
                provider="openai",
                model="gpt-3.5-turbo"
            )
        )
    )
    
    print(response.answer)
    for source in response.sources:
        print(f"来源: {source.document_title}")
"""

# TODO: 实现后取消以下注释
# from src.query.retriever import Retriever
# from src.query.llm_client import LLMClient
# from src.query.qa_engine import QAEngine
# from src.query.service import RAGQueryService

__all__ = [
    # "Retriever",
    # "LLMClient",
    # "QAEngine",
    # "RAGQueryService",
]