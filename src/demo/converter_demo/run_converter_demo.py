import sys
import os
import time
from pathlib import Path

# ==========================================
# 关键路径配置 (解决 ModuleNotFoundError)
# ==========================================
# 获取当前脚本的绝对路径: src/demo/converter_demo/run_demo.py
current_file_path = Path(__file__).resolve()

# 向上回溯 3 级找到项目根目录 (RAG_System)
# parents[0] = converter_demo
# parents[1] = demo
# parents[2] = src
# parents[3] = RAG_System (项目根目录)
project_root = current_file_path.parents[3]

# 将项目根目录加入 Python 搜索路径
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ==========================================
# 正常导入项目模块
# ==========================================
try:
    from src.converter import (
        DocumentConverterService, 
        DocumentInput, 
        ConversionResult
    )
    from src.utils import ensure_directory
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print(f"当前 Python 路径: {sys.path}")
    sys.exit(1)

# --- 终端颜色配置 ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def save_markdown(content: str, output_path: Path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

def create_sample_files(target_dir: Path):
    """如果没有文件，创建一些样例文件供测试"""
    ensure_directory(target_dir)
    
    html_content = "<html><body><h1>测试Demo</h1><p>这是一个在子目录运行的测试。</p></body></html>"
    (target_dir / "sample_demo.html").write_text(html_content, encoding='utf-8')
    
    txt_content = "测试文本\n\n这是为了验证 demo 文件夹结构是否正常工作。"
    (target_dir / "sample_demo.txt").write_text(txt_content, encoding='utf-8')
    
    print(f"{Colors.WARNING}已创建样例文件到: {target_dir.name}/{Colors.ENDC}")

def run_demo():
    # 1. 设置输入输出目录 (相对于当前脚本)
    base_dir = current_file_path.parent
    input_dir = base_dir / "inputs"
    output_dir = base_dir / "outputs"
    
    # 确保目录存在
    ensure_directory(input_dir)
    ensure_directory(output_dir)

    print(f"{Colors.HEADER}=== Converter Demo (Local Mode) ==={Colors.ENDC}")
    print(f"工作目录: {base_dir}")
    print(f"输入目录: ./inputs")
    print(f"输出目录: ./outputs\n")

    # 如果输入目录为空，创建样例
    if not any(input_dir.iterdir()):
        create_sample_files(input_dir)

    # 2. 初始化服务
    service = DocumentConverterService()
    
    # 3. 扫描并转换
    valid_extensions = {'.pdf', '.html', '.htm', '.txt', '.md'}
    files = [f for f in input_dir.iterdir() if f.suffix.lower() in valid_extensions]
    
    if not files:
        print(f"{Colors.WARNING}inputs 目录中没有找到支持的文件。{Colors.ENDC}")
        return

    for f in files:
        print(f"正在处理: {Colors.BLUE}{f.name}{Colors.ENDC}...", end="", flush=True)
        
        try:
            start_time = time.time()
            # 转换
            result = service.convert_document(DocumentInput(file_path=str(f)))
            duration = (time.time() - start_time) * 1000
            
            if result.success:
                out_path = output_dir / f"{f.stem}.md"
                save_markdown(result.document.content, out_path)
                print(f" {Colors.GREEN}✔ 完成 ({duration:.0f}ms){Colors.ENDC}")
            else:
                print(f" {Colors.FAIL}✘ 失败: {result.message}{Colors.ENDC}")
                
        except Exception as e:
            print(f" {Colors.FAIL}✘ 异常: {e}{Colors.ENDC}")

    print(f"\n{Colors.GREEN}演示结束。请查看 outputs 文件夹。{Colors.ENDC}")

if __name__ == "__main__":
    run_demo()