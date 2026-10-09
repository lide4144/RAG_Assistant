#!/usr/bin/env python3
"""
RAG存储模块演示脚本

从storage_demo/inputs目录读取真实的Markdown文件，
进行分块、向量化，并存储到ChromaDB，最后进行语义搜索演示。

运行方式：
    python -m src.demo.storage_demo.run_storage_demo

依赖：
    pip install chromadb sentence-transformers

功能流程：
1. 自动扫描 storage_demo/inputs 目录中的Markdown文件
2. 读取并解析Markdown文档
3. 自动分块并向量化
4. 存储到ChromaDB向量数据库
5. 执行语义搜索演示
6. 将结果保存到 storage_demo/outputs
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List

# ==========================================
# 路径配置
# ==========================================
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parents[3]

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ==========================================
# 导入模块
# ==========================================
try:
    from src.models.schemas import (
        MarkdownDocument,
        BaseMetadata,
        SourceInfo,
        FileType,
        StorageInput,
    )
    from src.storage import RAGStorageService, StorageServiceConfig
    from src.utils import ensure_directory
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print(f"当前 Python 路径: {sys.path}")
    sys.exit(1)

# ==========================================
# 终端颜色配置
# ==========================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_section(text: str):
    """打印章节"""
    print(f"\n{Colors.CYAN}>>> {text}{Colors.ENDC}")


def print_success(text: str):
    """打印成功消息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """打印错误消息"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str):
    """打印警告消息"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def find_markdown_files(inputs_dir: Path) -> List[Path]:
    """
    查找inputs目录中的Markdown文件
    
    Args:
        inputs_dir: inputs目录路径
    
    Returns:
        Markdown文件路径列表
    """
    if not inputs_dir.exists():
        return []
    
    # 查找所有.md文件
    md_files = list(inputs_dir.glob("*.md"))
    return md_files


def create_markdown_document(md_file: Path) -> MarkdownDocument:
    """
    从Markdown文件创建MarkdownDocument对象
    
    Args:
        md_file: Markdown文件路径
    
    Returns:
        MarkdownDocument对象
    """
    # 读取文件内容
    content = md_file.read_text(encoding="utf-8")
    
    # 提取标题（从第一行）
    title = md_file.stem
    first_line = content.split('\n')[0] if content else ""
    if first_line.startswith('#'):
        title = first_line.lstrip('#').strip()
    
    # 创建文档对象
    doc = MarkdownDocument(
        document_id=md_file.stem,
        content=content,
        metadata=BaseMetadata(
            title=title,
            language="zh" if any(ord(c) > 127 for c in content[:100]) else "en",
        ),
        source_info=SourceInfo(
            original_file_path=str(md_file),
            original_file_type=FileType.MARKDOWN,
            original_file_size_bytes=len(content.encode("utf-8")),
            original_file_hash=str(hash(content)),
            conversion_timestamp=datetime.fromtimestamp(md_file.stat().st_mtime),
        ),
        word_count=len(content),
    )
    
    return doc


def create_sample_markdown_file(inputs_dir: Path) -> Path:
    """
    创建一个示例Markdown文件用于演示
    
    Args:
        inputs_dir: inputs目录
    
    Returns:
        创建的文件路径
    """
    ensure_directory(inputs_dir)
    
    sample_content = """# RAG系统演示文档

## 什么是RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是一种结合了信息检索和文本生成的AI技术。

它通过以下步骤工作：
1. 文档转换：将各种格式的文档转换为统一的Markdown格式
2. 文档分块：将长文档切分成适合处理的小块
3. 向量化：将文本块转换为数值向量表示
4. 存储：将向量存储到向量数据库中
5. 检索：根据查询找到最相关的文档块
6. 生成：基于检索到的内容生成回答

## RAG的优势

相比传统的纯生成模型，RAG具有以下优势：

- **知识更新快**：可以随时添加新文档，无需重新训练模型
- **可解释性强**：可以追溯答案来源，提供引用
- **降低幻觉**：基于真实文档内容回答，减少编造信息
- **领域适应性好**：通过添加领域文档即可适应特定领域

## 应用场景

RAG技术广泛应用于：

1. **企业知识库问答**：帮助员工快速找到公司内部文档中的信息
2. **学术研究助手**：辅助研究人员查找和总结相关论文
3. **客户服务系统**：基于产品文档回答客户问题
4. **法律文档分析**：快速检索和分析法律条文

## 技术挑战

当前RAG系统面临的挑战包括：

- 如何进行最优的文档分块
- 如何选择合适的向量化模型
- 如何平衡检索精度和召回率
- 如何处理多语言和多模态内容

## 未来展望

RAG技术仍在快速发展，未来的研究方向包括：

- 更智能的分块策略
- 混合检索方法（关键词+语义）
- 多跳推理能力
- 与大语言模型的深度集成
"""
    
    sample_file = inputs_dir / "rag_system_demo.md"
    sample_file.write_text(sample_content, encoding="utf-8")
    
    return sample_file


def save_search_results(outputs_dir: Path, query: str, results: list, query_num: int):
    """
    保存搜索结果到文件
    
    Args:
        outputs_dir: 输出目录
        query: 查询文本
        results: 搜索结果列表
        query_num: 查询编号
    """
    ensure_directory(outputs_dir)
    
    output_file = outputs_dir / f"search_results_{query_num}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"查询: {query}\n")
        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"[{i}] 相似度: {result.similarity_score:.3f}\n")
            f.write(f"文档ID: {result.document_id}\n")
            if result.section_title:
                f.write(f"章节: {result.section_title}\n")
            f.write(f"内容:\n{result.content}\n")
            f.write("\n" + "-"*70 + "\n\n")


def run_demo():
    """运行完整的存储演示流程"""
    base_dir = current_file_path.parent
    inputs_dir = base_dir / "inputs"
    outputs_dir = base_dir / "outputs"
    
    print_header("RAG存储模块演示")
    
    print(f"项目根目录: {project_root}")
    print(f"演示目录: {base_dir}")
    print(f"输入目录: {inputs_dir}")
    print(f"输出目录: {outputs_dir}")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 确保目录存在
    ensure_directory(inputs_dir)
    ensure_directory(outputs_dir)
    
    # ==========================================
    # 步骤1: 查找Markdown文件
    # ==========================================
    print_section("步骤1: 查找Markdown文档")
    
    md_files = find_markdown_files(inputs_dir)
    
    if not md_files:
        print_warning(f"未在 {inputs_dir} 中找到Markdown文件")
        print("将创建一个示例文档用于演示...")
        
        sample_file = create_sample_markdown_file(inputs_dir)
        md_files = [sample_file]
        
        print_success(f"已创建示例文件: {sample_file.name}")
        print(f"\n💡 提示: 您可以将Markdown文件放入 {inputs_dir} 目录")
        print(f"   或者先运行转换模块生成Markdown文件")
    else:
        print_success(f"找到 {len(md_files)} 个Markdown文件:")
        for f in md_files:
            size_kb = f.stat().st_size / 1024
            print(f"  • {Colors.BLUE}{f.name}{Colors.ENDC} ({size_kb:.1f} KB)")
    
    # ==========================================
    # 步骤2: 读取并解析文档
    # ==========================================
    print_section("步骤2: 读取并解析文档")
    
    documents = []
    for md_file in md_files:
        try:
            doc = create_markdown_document(md_file)
            documents.append(doc)
            print(f"  ✓ {doc.metadata.title[:50]}... ({len(doc.content)} 字符)")
        except Exception as e:
            print_error(f"读取失败 {md_file.name}: {e}")
    
    if not documents:
        print_error("没有成功读取任何文档")
        return
    
    print_success(f"成功读取 {len(documents)} 个文档")
    
    # ==========================================
    # 步骤3: 创建存储服务
    # ==========================================
    print_section("步骤3: 初始化RAG存储服务")
    
    # 使用项目data目录存储向量数据库（持久化）
    vectordb_dir = project_root / "data" / "vectordb" / "storage_demo"
    ensure_directory(vectordb_dir)
    
    print(f"向量数据库目录: {vectordb_dir}")
    print("\n配置参数:")
    print(f"  • 块大小: 512 字符")
    print(f"  • 块重叠: 50 字符")
    print(f"  • 分割方式: paragraph（段落）")
    print(f"  • 最小块大小: 0（防止数据丢失）")
    print(f"  • 向量化模型: paraphrase-multilingual-MiniLM-L12-v2")
    print(f"  • 向量数据库: ChromaDB")
    
    try:
        config = StorageServiceConfig(
            # 分块配置
            chunk_size=512,
            chunk_overlap=50,
            split_by="paragraph",
            respect_sections=True,
            min_chunk_size=0,          # 防止数据丢失
            merge_small_chunks=True,   # 合并小块
            
            # 向量化配置
            embedding_provider="sentence-transformers",
            embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
            
            # 存储配置
            vector_db_type="chroma",
            persist_directory=str(vectordb_dir),  # 使用项目data目录
            default_collection="demo_papers",
        )
        
        print("\n正在初始化服务...")
        print_warning("首次运行需要下载向量化模型（约90MB），请耐心等待...")
        
        start_time = time.time()
        service = RAGStorageService(config)
        init_time = (time.time() - start_time) * 1000
        
        print_success(f"服务初始化完成 ({init_time:.0f}ms)")
        
    except Exception as e:
        print_error(f"初始化失败: {e}")
        print("\n可能的原因:")
        print("  1. 未安装必要的依赖包")
        print("     解决: pip install chromadb sentence-transformers")
        print("  2. 网络问题导致模型下载失败")
        print("     解决: 检查网络连接或配置代理")
        import traceback
        traceback.print_exc()
        return
    
    # ==========================================
    # 步骤4: 存储文档
    # ==========================================
    print_section("步骤4: 分块、向量化并存储文档")
    
    print("处理流程:")
    print("  1️⃣ 文档分块 → 2️⃣ 文本向量化 → 3️⃣ 存储到向量数据库\n")
    
    try:
        storage_input = StorageInput(
            documents=documents,
            collection_name="demo_papers",
        )
        
        start_time = time.time()
        result = service.store_documents(storage_input)
        duration = (time.time() - start_time) * 1000
        
        if result.success:
            print_success("存储完成！")
            print(f"\n存储统计:")
            print(f"  • 总文档数: {result.total_documents}")
            print(f"  • 功文档数: {result.success_documents}")
            print(f"  • 总文本块数: {result.total_chunks}")
            print(f"  • 处理耗时: {duration:.0f}ms")
            print(f"  • 平均每块: {duration/result.total_chunks:.0f}ms")
            
            print(f"\n各文档详情:")
            for info in result.documents_info:
                status = "✓" if info.success else "✗"
                color = Colors.GREEN if info.success else Colors.FAIL
                doc = next((d for d in documents if d.document_id == info.document_id), None)
                title = doc.metadata.title[:40] if doc else info.document_id
                print(f"  {color}{status}{Colors.ENDC} {title}: {info.chunks_count} 个块")
        else:
            print_error(f"存储失败: {result.message}")
            return
            
    except Exception as e:
        print_error(f"存储过程出错: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ==========================================
    # 步骤5: 语义搜索演示
    # ==========================================
    print_section("步骤5: 语义搜索演示")
    
    # 根据文档内容智能选择查询
    queries = [
        "什么是深度学习？",
        "RAG系统是如何工作的？",
        "知识图谱有什么应用？",
    ]
    
    # 如果有真实文档，使用更相关的查询
    if any("Large Language Model" in doc.content for doc in documents):
        queries = [
            "large language model agents",
            "game applications",
            "what are the challenges",
        ]
    
    print(f"将执行 {len(queries)} 个查询，每个返回 Top-3 最相关的文本块\n")
    
    for i, query in enumerate(queries, 1):
        print(f"{Colors.BOLD}查询 {i}: 「{query}」{Colors.ENDC}")
        
        try:
            start_time = time.time()
            results = service.search(query, top_k=3)
            search_time = (time.time() - start_time) * 1000
            
            if results:
                print(f"  搜索耗时: {search_time:.0f}ms，找到 {len(results)} 个结果\n")
                
                # 保存搜索结果
                save_search_results(outputs_dir, query, results, i)
                
                for j, result in enumerate(results, 1):
                    # 获取来源文档
                    doc_id = result.document_id
                    doc = next((d for d in documents if d.document_id == doc_id), None)
                    doc_title = doc.metadata.title[:30] if doc else doc_id
                    
                    # 显示结果
                    print(f"  [{j}] 相似度: {Colors.GREEN}{result.similarity_score:.3f}{Colors.ENDC}")
                    print(f"      来源: {doc_title}")
                    if result.section_title:
                        print(f"      章节: {result.section_title}")
                    
                    # 显示内容预览
                    content = result.content.replace('\n', ' ').strip()
                    if len(content) > 120:
                        content = content[:120] + "..."
                    print(f"      内容: {Colors.CYAN}{content}{Colors.ENDC}")
                    print()
            else:
                print_warning("  未找到相关结果")
                
        except Exception as e:
            print_error(f"  搜索失败: {e}")
        
        print()
    
    print_success(f"搜索结果已保存到: {outputs_dir}")
    
    # ==========================================
    # 步骤6: 显示统计信息
    # ==========================================
    print_section("步骤6: 系统统计信息")
    
    try:
        stats = service.get_collection_stats()
        print("向量数据库统计:")
        for key, value in stats.items():
            print(f"  • {key}: {value}")
    except Exception as e:
        print_warning(f"无法获取统计信息: {e}")
    
    # ==========================================
    # 完成
    # ==========================================
    print_header("演示完成")
    
    print("✨ 您已成功完成RAG存储模块的完整演示流程！\n")
    
    print("演示内容回顾:")
    print("  ✓ 从独立inputs目录读取Markdown文档")
    print("  ✓ 智能分块（防止数据丢失）")
    print("  ✓ 文本向量化（384维向量）")
    print("  ✓ 存储到ChromaDB向量数据库")
    print("  ✓ 语义搜索和相似度计算")
    print("  ✓ 搜索结果保存到outputs目录")
    
    print(f"\n📂 文件位置:")
    print(f"  • 输入文件: {inputs_dir}")
    print(f"  • 输出文件: {outputs_dir}")
    print(f"  • 向量数据库: {vectordb_dir}")
    
    print(f"\n💡 提示:")
    print(f"  • 将Markdown文件放入 inputs/ 目录进行处理")
    print(f"  • 搜索结果保存在 outputs/ 目录")
    print(f"  • 向量数据库持久化保存在 data/vectordb/storage_demo/")
    print(f"  • 下次运行会复用已有的向量数据库，无需重新向量化")
    
    print(f"\n📚 下一步:")
    print(f"  • 添加更多文档: 将Markdown文件放入 {inputs_dir}")
    print(f"  • 调整参数: 修改 chunk_size、embedding_model 等")
    print(f"  • 集成到应用: 参考 src/storage/service.py 的API")


if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}用户中断{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.FAIL}程序异常: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()