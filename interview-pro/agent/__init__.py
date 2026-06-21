"""面试官Pro — agent 核心模块。

模块清单：
- database: SQLite + FTS5 全文检索
- question_bank: 题库 CRUD
- search: FTS5 搜索 + BM25 排序
- interviewer: 模拟面试引擎
- evaluator: AI 答案评分
- categorizer: 题目分类（主题/难度/类型）
- reporter: 报告与统计分析
- logger: 结构化日志
- retriever: 经验检索层（Plan C 静态路由 + Plan A 预留向量搜索）
- mocker: 模拟模式生成引擎（AI 代入刘一鸣人设生成面试回答）
- knowledge_base: 知识库（项目事实存储与检索，与身份层解耦）
- roles: 岗位体系（岗位→阶段→分类三层组织，读 config/roles.yaml）
"""
