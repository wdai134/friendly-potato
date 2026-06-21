"""题目分类器 — 分类/难度/标签体系管理。

提供分类枚举、统计、标签查询功能。
分类体系通过 config/topics.yaml 配置，此处提供运行时接口。
"""

from agent.database import get_connection


# 内置默认分类体系
DEFAULT_CATEGORIES = [
    "Python基础", "算法与数据结构", "系统设计", "数据库",
    "网络协议", "操作系统", "机器学习", "深度学习",
    "NLP自然语言处理", "计算机视觉", "前端开发", "后端开发",
    "DevOps运维", "行为面试", "项目经验", "其他",
]

DIFFICULTY_LEVELS = ["初级", "中等", "高级", "专家"]


def get_categories() -> list[str]:
    """获取当前题库中所有分类（运行时从数据中提取）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM questions ORDER BY category"
    ).fetchall()
    conn.close()

    cats = [r["category"] for r in rows if r["category"]]
    return cats or DEFAULT_CATEGORIES


def get_category_stats() -> list[dict]:
    """各分类题目数量统计。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT category, COUNT(*) as count,
               SUM(CASE WHEN difficulty='初级' THEN 1 ELSE 0 END) as junior,
               SUM(CASE WHEN difficulty='中等' THEN 1 ELSE 0 END) as mid,
               SUM(CASE WHEN difficulty='高级' THEN 1 ELSE 0 END) as senior,
               SUM(CASE WHEN difficulty='专家' THEN 1 ELSE 0 END) as expert
        FROM questions
        GROUP BY category
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_tags() -> list[str]:
    """获取所有出现过的标签。"""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT tags FROM questions").fetchall()
    conn.close()

    all_tags = set()
    import json
    for r in rows:
        try:
            tags = json.loads(r["tags"])
            all_tags.update(tags)
        except (json.JSONDecodeError, TypeError):
            continue

    return sorted(all_tags)


def auto_categorize(title: str, content: str = "") -> dict:
    """基于关键词的简单自动分类。

    后续可接入 DeepSeek AI 做语义分类。
    返回: {"category": str, "difficulty": str, "tags": list[str]}
    """
    text = (title + " " + content).lower()

    # 关键词 → 分类映射（覆盖全部 15 个活跃分类，"其他"为兜底）
    keyword_map = {
        "Python基础": ["python", "列表", "字典", "装饰器", "生成器", "迭代器", "lambda", "闭包", "gil"],
        "算法与数据结构": ["排序", "查找", "二叉树", "链表", "哈希", "动态规划", "递归", "复杂度", "堆栈"],
        "系统设计": ["架构", "微服务", "分布式", "高并发", "负载均衡", "缓存", "消息队列", "restful"],
        "数据库": ["sql", "索引", "事务", "acid", "nosql", "mysql", "redis", "mongodb", "join"],
        "网络协议": ["http", "tcp", "udp", "dns", "websocket", "rest", "osi", "https"],
        "操作系统": ["进程", "线程", "内存", "死锁", "调度", "文件系统", "io", "并发"],
        "机器学习": ["回归", "分类", "聚类", "过拟合", "特征", "损失函数", "梯度", "svm"],
        "深度学习": ["神经网络", "cnn", "rnn", "transformer", "attention", "反向传播", "激活函数"],
        "NLP自然语言处理": ["nlp", "词向量", "bert", "gpt", "token", "分词", "序列", "文本"],
        "计算机视觉": ["cv", "opencv", "图像", "目标检测", "分割", "卷积", "特征提取", "人脸识别"],
        "前端开发": ["html", "css", "javascript", "react", "vue", "dom", "组件", "渲染", "响应式", "ui"],
        "后端开发": ["api", "flask", "django", "spring", "认证", "授权", "中间件", "网关", "接口"],
        "DevOps运维": ["docker", "kubernetes", "ci", "cd", "部署", "监控", "日志", "自动化", "容器"],
        "行为面试": ["团队", "冲突", "失败", "成功", "领导", "沟通", "挑战"],
        "项目经验": ["项目", "开发", "上线", "迭代", "需求", "优化", "重构", "测试", "交付"],
    }

    # 匹配分类
    max_score = 0
    best_category = "其他"
    for cat, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > max_score:
            max_score = score
            best_category = cat

    # 难度判断：文本越长、关键词越多 → 难度越高
    if max_score >= 3:
        difficulty = "高级"
    elif max_score >= 1:
        difficulty = "中等"
    else:
        difficulty = "初级"

    # 提取标签
    tags = []
    for cat, keywords in keyword_map.items():
        for kw in keywords:
            if kw in text and kw not in tags:
                tags.append(kw)
    tags = tags[:5]  # 最多5个标签

    return {"category": best_category, "difficulty": difficulty, "tags": tags}
