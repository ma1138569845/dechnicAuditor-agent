# 能源审计报告参考库 — RAG检索系统

## 数据概览

- 32份山东省直能源审计报告
- 按章节切分为 286 chunks
- 三级标签：audit_type → institution_category → specific_type
- 存储：Qdrant collection `energy_audit_reports` @ 10.10.2.55:6333

## 标签分布

| 类别 | 报告数 | 具体类型 |
|------|--------|----------|
| 党政机关 | 12 | 人社厅/法院/纪委监委/司法厅/市场监管局/生态环境厅/科技厅/科协/信访局/监狱局/贸促会/共青团 |
| 教育 | 4 | 济南大学/技师学院/省委党校/东营职业学院 |
| 医疗 | 2 | 省二院/省卫健委 |
| 场馆机构 | 2 | 图书馆/老干部活动中心 |
| 体育 | 1 | 体育训练中心 |

## 检索入口

```python
from rag.rag_search import search_reports, search_for_chapter
```

### 三层兜底

```
search_reports(query, tags)
  ├─ Layer 0: Qdrant 标签直查（filter by tags，无需 API key）
  ├─ Layer 1: Qdrant 向量检索（语义匹配，需要 API key）
  └─ Layer 2: 本地知识库关键词搜索
       ├─ references/chapter*.md（能源审计章节指南）
       └─ Obsidian wiki E:/data/wiki（AI Agent/LLM 研究笔记）
```

### Obsidian wiki 集成

`rag/rag_search.py` 的 Layer 2 额外搜素 `E:/data/wiki` 下的所有 `.md` 文件：

- 递归遍历全部子目录（entities/, concepts/, comparisons/, queries/）
- 自动排除 `_meta/`, `raw/`, `未命名.base/`, `.obsidian/` 及 `index.md`, `log.md`, `SCHEMA.md`
- 解析 YAML frontmatter 的 `title:` 字段作为章节名
- 结果标记 `source: obsidian_wiki`，与原 `local_wiki` 来源可区分
- 关键字匹配（全词命中计数排序），上限10条

### 常用调用

```python
# 查同类机构同章节作为写作参考
ref = search_for_chapter('第2章', {'institution_category': '医疗'})

# 验证指标计算（查同类医院第5章对标）
ref = search_for_chapter('第5章', {'specific_type': '医院'}, '单位建筑面积')

# 参考节能建议
ref = search_for_chapter('第7章', {'institution_category': '教育'}, 'LED')
```

## 嵌入报告生成流程

```python
# 生成前设标签
report_data['tags'] = {'institution_category': '医疗', 'specific_type': '医院'}

# LLM生成某章前检索参考
builder = WordReportBuilder('公共机构')
builder.set_data(report_data)
ref = builder.get_chapter_reference('第2章', '公共机构基本情况')
# → 返回 Markdown 参考文本，嵌入 LLM prompt
```

## 入库脚本

```bash
python rag/ingestion/ingest_reports.py   # 旧 tools/energy_audit/ingest_reports.py 为 DEPRECATED 壳
```

分类规则：从文件名关键词匹配（医院/大学/法院/科技厅…）。
Embedding: DashScope `text-embedding-v3`, 1024维。
