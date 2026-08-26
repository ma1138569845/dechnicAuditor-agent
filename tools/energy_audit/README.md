# 能源审计工具包

本工具包提供完整的能源审计解决方案，支持三种类型的能源审计报告生成。

## 功能概述

### 支持的审计类型
1. **公共机构能源审计** - 政府机关、事业单位等
2. **公共建筑能源审计** - 商业建筑、办公大楼等
3. **工业企业能源审计** - 工厂、生产线等

### 核心功能
- Excel数据处理和清洗
- PostgreSQL数据库查询
- RAG知识检索（基于Qdrant向量数据库）
- 标准化报告生成
- 能耗指标计算
- 数据可视化

## 安装要求

### Python依赖
```bash
pip install pandas numpy psycopg2-binary llama-index qdrant-client
```

### 环境变量配置
```bash
# PostgreSQL配置
export PG_HOST="localhost"
export PG_PORT="5432"
export PG_DATABASE="energy_audit"
export PG_USER="readonly_user"
export PG_PASSWORD="your_password"

# RAG系统配置
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export DASHSCOPE_API_KEY="your_dashscope_api_key"
export QDRANT_URL="http://10.10.2.55:6333"
export QDRANT_COLLECTION="knowledge_segment_qwen"
```

## 快速开始

### 1. 基础使用

```python
from tools.energy_audit import EnergyAuditPipeline

# 创建审计流程
pipeline = EnergyAuditPipeline('公共机构')

# 加载Excel数据
pipeline.load_excel_data('能耗数据.xlsx')

# 连接数据库
pipeline.connect_database({
    'host': 'localhost',
    'port': '5432',
    'database': 'energy_audit',
    'user': 'readonly_user',
    'password': 'your_password'
})

# 查询能耗数据
pipeline.query_energy_data('2023-01-01', '2023-12-31')

# 生成报告
pipeline.generate_report('公共机构能源审计报告.md')
```

### 2. 单独使用各个工具

#### Excel数据处理
```python
from tools.energy_audit import ExcelDataProcessor

processor = ExcelDataProcessor('能耗数据.xlsx')
data = processor.read_excel()
cleaned_data = processor.clean_data()
indicators = processor.calculate_energy_indicators(
    cleaned_data,
    energy_col='能耗量',
    area_col='建筑面积',
    people_col='用能人数'
)
```

#### PostgreSQL查询
```python
from tools.energy_audit import PgDataQuery

with PgDataQuery(config) as db:
    energy_data = db.get_energy_consumption('2023-01-01', '2023-12-31')
    equipment_data = db.get_equipment_info(equipment_type='空调')
    statistics = db.get_energy_statistics(year=2023, group_by='month')
```

#### RAG知识检索
```python
from tools.energy_audit import RAGKnowledgeRetrieval

rag = RAGKnowledgeRetrieval()
rag.initialize()

# 搜索相关标准
results = rag.search_standards('公共机构', '能耗指标')

# 搜索计算方法
results = rag.search_calculation_methods('人均综合能耗')

# 搜索最佳实践
results = rag.search_best_practices('公共机构', '空调系统')
```

#### 报告生成
```python
from tools.energy_audit import ReportGenerator

generator = ReportGenerator('公共机构')
generator.set_report_data(report_data)
generator.save_report('公共机构能源审计报告.md')
```

## 工具包结构

```
tools/energy_audit/
├── __init__.py              # 主入口和工具包初始化
├── excel_processor.py       # Excel数据处理工具
├── pg_query.py             # PostgreSQL数据查询工具
├── rag_retrieval.py        # RAG知识检索工具
├── report_generator.py     # 报告生成工具
├── config.yaml            # 配置文件
└── README.md              # 本说明文件
```

## 配置说明

### 数据库配置
在 `config.yaml` 中配置PostgreSQL连接信息：

```yaml
database:
  host: "localhost"
  port: "5432"
  database: "energy_audit"
  user: "readonly_user"
  password: ""
  sslmode: "prefer"
```

### RAG系统配置

与 Desktop 知识库共用 `{HERMES_HOME}/config.yaml` 的 `knowledge_base:`（不要再配一份 `rag.qdrant_url`）：

```yaml
knowledge_base:
  qdrant_host: "10.10.2.55"
  qdrant_port: 6334
  qdrant_http_port: 6333
  summary_model: "deepseek-v4-flash"
  energy_audit_collection: "knowledge_segment_qwen"
```

密钥放 `{HERMES_HOME}/.env`：`DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`。

## 报告结构

### 公共机构能源审计报告
1. 封面
2. 目录
3. 第1章 能源审计执行概要
4. 第2章 公共机构单位概况
5. 第3章 能源资源管理状况
6. 第4章 能源资源计量及统计状况
7. 第5章 能源资源消费/消耗指标分析
8. 第6章 主要能源资源利用系统分析
9. 第7章 节能效果与节能潜力分析
10. 第8章 审计结论

### 公共建筑能源审计报告
1. 封面
2. 目录
3. 第1章 审计执行概要
4. 第2章 建筑概况
5. 第3章 能源管理状况
6. 第4章 能源计量与统计
7. 第5章 能源消耗分析
8. 第6章 能源系统分析
9. 第7章 节能潜力分析
10. 第8章 审计结论与建议

### 工业企业能源审计报告
1. 封面
2. 目录
3. 第1章 审计执行概要
4. 第2章 企业概况
5. 第3章 能源管理状况
6. 第4章 能源计量与统计
7. 第5章 能源消耗分析
8. 第6章 主要用能系统分析
9. 第7章 节能潜力分析
10. 第8章 审计结论与建议

## 能耗指标计算

### 人均综合能耗
```
人均综合能耗 = 综合能耗总量(tce) / 用能人数(人)
```

### 单位建筑面积能耗
```
单位建筑面积能耗 = 综合能耗总量(tce) / 建筑面积(m²)
```

### 单位建筑面积电耗
```
单位建筑面积电耗 = 电力消耗量(kWh) / 建筑面积(m²)
```

### 人均电耗
```
人均电耗 = 电力消耗量(kWh) / 用能人数(人)
```

## 标准规范参考

### 国家标准
- GB/T 13234-2018 用能单位节能量计算方法
- GB/T 15587-2008 工业企业能源管理导则
- GB/T 23331-2012 能源管理体系要求
- GB 50189-2015 公共建筑节能设计标准

### 行业标准
- 公共机构能源审计技术导则
- 公共建筑能源审计技术导则
- 工业企业能源审计技术导则

### 地方标准
- 各省市公共机构能源审计实施细则
- 各省市公共建筑节能设计标准

## 注意事项

1. **数据安全**：确保数据库用户只有只读权限
2. **API密钥**：妥善保管DeepSeek和DashScope的API密钥
3. **数据验证**：在生成报告前验证数据的完整性和准确性
4. **标准更新**：定期检查相关标准的更新情况
5. **报告审核**：生成的报告需要人工审核后才能正式提交

## 故障排除

### 数据库连接失败
- 检查数据库配置是否正确
- 确认数据库服务是否运行
- 验证用户权限

### RAG系统初始化失败
- 检查API密钥是否正确
- 确认Qdrant服务是否可访问
- 验证集合名称是否正确

### 报告生成错误
- 检查数据格式是否符合要求
- 确认模板文件是否存在
- 验证输出路径是否有写入权限

## 技术支持

如有问题或建议，请联系开发团队。

## 版本历史

- v1.0.0 (2024-01-01) - 初始版本
  - 支持三种审计类型
  - 实现基础数据处理功能
  - 集成RAG知识检索
  - 提供标准化报告生成
