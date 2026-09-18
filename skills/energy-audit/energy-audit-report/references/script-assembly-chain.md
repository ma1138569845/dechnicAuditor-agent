# 装配脚本链（build → finalize → asserts）—— 2026-09-17 起装配+收尾主链

> 定位：报告"版式装配 + 收尾"的**默认路径**；内容层不变（正文仍由 LLM 逐章写 `chapter_md/chN.md`）。
> office_editor 路径降为**备用**（存量报告定点修改、应急）。
> 首次验证（2026-09-17，烟台经开区法院）：与 45 页终稿逐段文本 diff=0、交付断言 10/10、
> 单份装配+收尾 ≈30 秒（不含写章）。

## 两条命令 + 一个断言器

```bash
# ① 装配（一次构建：封面/信息表/目录/8章/附录/页眉水印页脚）
python skills/energy-audit/energy-audit-report/scripts/build_energy_audit_docx.py \
    --project-dir <项目目录> [--out <docx路径>]

# ② 收尾（Word COM 一次：刷目录域缓存 → 保存 → ExportAsFixedFormat → 封面盖章）
python skills/energy-audit/energy-audit-report/scripts/finalize_energy_audit_pdf.py \
    --project-dir <项目目录> [--no-seal] [--seal-text 审计机构名]

# ③ 交付断言（每份必跑；docx 级 10 项硬检查 + PDF 级度量）
python skills/energy-audit/energy-audit-report/scripts/ea_docx_asserts.py \
    <报告.docx> [--pdf <报告.pdf>] [--expect pages=45]
```

默认输出：`<项目>/output/_script_build/<单位全称>能源审计报告.docx|pdf`。

**交付归置（2026-09-17 定；烟台法院项目首用）**：对外交付时，把 docx + 签章 PDF **复制**到 `<项目>/output/交付件/<单位全称>能源审计报告.docx|pdf`——`交付件/` 为唯一对外出口；沙箱正本（`_script_build` 等）保留不动，**复制不移动、不覆盖、不删除**既有文件。

## 输入契约（项目目录）

| 输入 | 说明 |
|---|---|
| `data.json` | base（unit_name/audit_org_name/audit_org_address/contact/phone/report_date）、energy_yearly（审计期间年）、audit_team、cooperation |
| `chapter_md/ch1..ch8.md` | LLM 逐章正文（第5章用 caliber 产出的 `ch5_import.md`，脚本优先匹配 `chN_import.md`）。`ch5_import.md` 由 `ea-calculation/scripts/prepare_chapter_md.py <项目名>` 就位（不覆盖作者已并入叙述段的版本；退出码 2 = 装配稿早于计算产物需人工确认） |
| `chapter_md/appendix.md` | 附录（7 附录约定；有发票插发票附录） |
| `report_images.json` | 图清单：`{images: [{caption: "图X.Y …", src: 相对路径}]}`；caption 须与 md 图注行**精确一致**（`图4.1` 双图=两条同 caption 记录） |
| `assets/omml_formulas.json` | OMML 公式库（当前法院/机关型 5 个）。其他机构类型在其项目首次使用时从同类成品提取补入——同一 JSON 加键 `FORMULAn` 即可，无需改代码 |

## 装配覆盖（对齐 45 页终稿）

- 封面：3 空行 + 单位 22pt + 报告名 26pt + 审计期间 + 8 空行 + 机构/日期 + 分页；
- 三张信息表（机构/审计组/配合人员）；
- 目录页：'目  录'（无标题样式防自收录）+ TOC 域 `\o "1-3"`；**其后不插分页**（第1章同页顺延，复刻终稿）；
- 章节：H1 15pt 居中 / H2 14pt / H3 12pt；正文 1.5 行距 + 两端对齐 + 首行缩进 2 字符（firstLineChars=200）；表 Table Grid、12pt 居中、行高 1.01cm；图 12cm 独立居中段 + 图注段；公式三段式（按式→OMML 居中段→计算）；项目符号 Wingdings 圆点；
- 页眉（单位全称 + 两空格 + 能源审计报告，右对齐宋体 10.5pt + pBdr 底边线 + EAWatermark 水印 behindDoc）/ 页脚（— PAGE —）/ settings updateFields；
- 附录：'附录：' 总页（H1 样式、12pt 非粗、左对齐）+ 清单行（1.5 行距无缩进）+ H2 附录标题 + 附表题（居中加粗）+ 表格。

## 收尾（Word COM）要点

- 打开**必须传绝对路径**（相对路径 Word 按自身工作目录解析 → 报"找不到您的文件"）。
- 流程：`TablesOfContents(1).Update()` + `Fields.Update()` + `Repaginate()` → `Save()` → `ExportAsFixedFormat(pdf, 17)`。
- **Word 保存会剥离 `<w:updateFields>`** → 收尾脚本 zip 级自动补写（与 45 页终稿终态一致）。
- 盖章：`tools/energy_audit/assets/default_seal.png` 存在即用真实印章（忽略 seal_text），否则按 `base.audit_org_name` 生成 480×480 占位红章；位置 = 封面水平居中、y≈0.66·页高、宽 120pt。

## 已知偏差（vs 45 页终稿；验收口径 = 断言全绿 + 文本一致 + 页数 ±2）

1. 页数 44 vs 45（±1 容差内）：TOC 区占用 +1 页、ch6 −1、ch7 +1、ch8 −1、附录 −1（净 −1）。
2. 表列宽：脚本 = 全幅均分（8312 twips）；终稿 = 导入链自然宽（3280~8340 不等）。行数/行高/单元格格式一致。
3. Word 收尾按字体脚本边界**拆分 run**（渲染不变）：对收尾后 docx 的文本正则必须按段落拼接 `w:t` 后再匹配（断言器图注度量已按此实现）。
4. 目录占位文本"（打开文档后目录将自动更新）"由收尾刷新为缓存条目；断言器区分"未缓存占位（合法）"与"自收录错误"。

## 模板资产（随技能维护）

| 资产 | 来源 | 用途 |
|---|---|---|
| `assets/header_template.xml` | 烟台法院 45 页终稿 header（单位名→`{{UNIT}}` 占位、去 pStyle 引用） | 页眉文字 + 水印注入（zip 级替换 headerN.xml） |
| `assets/footer_template.xml` | 同上 footer（— PAGE —） | 页脚注入 |
| `assets/omml_formulas.json` | R7 终稿提取的 5 个已验证 OMML | `[FORMULAn]` 占位行注入 |

## 验证

- 单元：`pytest tests/skills/test_energy_audit_docx_build.py -q`（17 项：结构/样式/公式/图/附录/页眉/收尾 --help/缺键告警/变体注入）；
- E2E：法院项目全量重跑，对照 45 页终稿（文本 diff=0、断言全绿、耗时记录）；
- 交付：每份必跑断言器；数值断言仍走 `tools/energy_audit/report_qa.py`（口径不变）。

## 操作坑（实战记录）

- Word COM 一律绝对路径；收尾结束前用重试式原子替换（Word 关闭瞬间句柄未释放）。
- 断言/比对工具对"收尾后 docx"须按段落拼接文本（run 拆分，见偏差 3）。
- 封面签章图核验：PDF p1 应存在 480×480 图对象（ycenter≈0.66）。
