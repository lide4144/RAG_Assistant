"""
测试模块

包含系统各模块的单元测试和集成测试。

测试文件：
- test_converter.py: 文档转换模块测试
- test_storage.py: RAG存储模块测试
- test_query.py: RAG问答模块测试
- test_models.py: 数据模型测试
- test_integration.py: 集成测试

运行测试：
    # 运行所有测试
    pytest
    
    # 运行特定模块测试
    pytest tests/test_converter.py
    
    # 运行测试并生成覆盖率报告
    pytest --cov=src --cov-report=html
"""