# Word 公式编辑指南（第5章指标公式）

> 第5章 5.3 各指标段需要呈现计算公式（Word 数学公式对象，分式+下标渲染）。

## 方案选择（按优先级，2026-09-06 定）

| 方案 | 适用 | 说明 |
|------|------|------|
| **A. office_edit `doc_insert_math`（唯一首选）** | 报告生成流程中的 5.3 全部公式 | 引擎 C++ 层把 LaTeX 解析为 OMML，结构保证 Word 识别；经实测渲染为正常公式样式 |
| B. `fix_chapter5_formulas.py` 脚本 | **仅存量报告**后处理（已含文本公式的旧 docx） | zip+lxml 注入，需自行保证 xmlns:m 声明正确；新报告不得走此路径 |
| C. OfficeCLI equation | 无分式的简单式子 | 不支持分式（\frac 不解析、/ 不转 m:f，实测 m:f=0），5.3 公式禁用 |

**默认用方案 A**：在 author 写第5章 5.3 各指标段时，直接用 office_edit 工具集调用
`doc_insert_math` 插入公式（LaTeX 参数，见下表）。**不用**：
- 纯文本公式行（"Ejrcn=（E−Egn−Ejt）/M"）——非数学对象，Word 不渲染为公式样式，2026-09-06 起废除
- 事后 zip+lxml 注入（缺根 xmlns:m 声明时 Word 静默按普通文本渲染；声明写法错误时 Word 直接拒开）
- 截图/图片公式（模糊、不可检索、格式校验不过）

## doc_insert_math 调用方式

```json
office_edit(
  file_id=<报告 file_id>,
  operation="doc_insert_math",
  arguments={"idx": <段落结束位置，来自 doc_get_last_operable_pos 或上一写操作返回值>, "latex": "<LaTeX>"}
)
```

- idx 是 DOC 坐标，必须来自查询结果或上一次写操作返回值，勿按肉眼字符数/段落序号手算。
- 公式插入前先把"符号+中文定义"文本段（`Ejrcn——单位建筑面积非供暖能耗，……；`）照常写入，
  公式对象插在定义段之前或之后（与正式报告版式一致处）。
- 变量符号定义段仍用正文格式：变量符号 Times New Roman 斜体、中文定义与单位宋体 12pt；
  单位写法不加括号（`kgce/(m²·a)`，报告铁律）。

## 第5章公式清单（LaTeX 写法 + 符号与正式版一致）

| 指标 | LaTeX（doc_insert_math 用） | 变量 |
|------|------|------|
| 单位建筑面积非供暖能耗 5.3.1 | `E_{jrcn}=\frac{E-E_{gn}-E_{jt}}{M}` | E 综合能耗 kgce/a；Egn 供暖能耗；Ejt 交通能耗；M 建筑面积 m² |
| 常规用能系统单位建筑面积电耗 5.3.2 | `E_{ja}=\frac{E_{D}}{M}` | ED 电量总和 kWh/a（已剔供暖电耗）；M 建筑面积 |
| 人均综合能耗 5.3.3 | `E_{r}=\frac{E}{P}` | E 综合能耗 kgce/a；P 用能人数 p |
| 取水指标 5.3.4（按机构类型自适应，DB37/T 4452-2021） | 机关(7)：`V_{uc}=\frac{V_{k}}{N_{p}}`（m³/(人·a)）<br>高校(3)：`V_{u}=\frac{W_{u}}{N_{u}}`（Nu=统招生+留学生+0.5×教职工）<br>中小学/幼儿园(4)：`V_{s}=\frac{W_{u}}{N_{s}}`（Ns=非住宿生+2×住宿生+教职工）<br>医院(5)：`V_{z}=\frac{W_{z}}{\sum_{i=1}^{365}N_{i}}\times10^{3}`（L/(床·日)，ΣNi=全年实际开放床日数）<br>政务/场馆(6)：`V_{ui}=\frac{V_{j}}{N_{c}}\times1000`（L/(m²·a)） | 变量定义见 core/references/standards-values.md；不对标：政务/场馆（4452 无面积定额） |
| 单位采暖建筑面积供暖能耗 5.3.5 | `E_{gnm}=\frac{E_{gn}}{M_{gn}}` | Egn 供暖能耗 kgce/a；Mgn 采暖建筑面积 m² |

> 变量符号（Ejrcn/Eja/Er/Vuc/Egnm + 取水按类型 Vuc/Vu/Vs/Vz/Vui）以正式报告与 DB37/T 4452-2021 为准（2026-09-05 用户确认对齐；2026-09-05 晚按烟台法院正式版勘误：5.3.1=Ejrcn、5.3.2=Eja，此前 Ejfgn/Ejd 为误记）；报告中的符号不可自行改名。

## 方案 B：存量报告后处理（fix_chapter5_formulas.py）

仅用于修复**历史生成的报告**（5.3 还是文本公式的旧 docx）：

```bash
python skills/energy-audit/energy-audit-report/scripts/fix_chapter5_formulas.py <报告.docx> [--dry-run]
```

⚠ 该脚本历史上存在两类失败（2026-09-06 实测定位）：
1. 根元素用字符串/伪 QName 注入 `xmlns:m` → 生成 `ns0:m` 伪装属性 → **Word 拒开文件**；
2. 不声明 m 前缀（ns0/ns1 局部前缀）→ Word 能打开但**公式按普通文本渲染，不显示公式样式**。
正确声明方式（lxml）：序列化前 `etree.register_namespace('m', M_NS)`。
新报告一律走方案 A，不要依赖本脚本。

## 验证（必做）

1. `office_render(file_id, format="png")` 渲染后**必须视觉复核**渲染图（vision 不可用时让用户看图确认或对比引擎原生公式 docx），确认公式为分式+下标样式，而非文本/乱码。
2. 结构化抽查：解包 docx，公式段落应含 `m:oMath`（或 `m:oMathPara`）+ document.xml 根元素 `xmlns:m` 声明（doc_insert_math 自动满足）。
3. 渲染异常时：先用 `doc_insert_math` 重插（勿手动修 XML），仍异常则报告阻塞，不得交付未验证的公式。

## 附录：引擎原生 OMML 结构（参考，勿手写）

doc_insert_math 生成的公式（formula_ref 实测）结构特征：
根元素声明 `xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"`；
`w:p` 内直接 `m:oMath`；每个 `m:r` 含 `<m:rPr/><w:rPr/>`；`m:sSub` 含 `<m:sSubPr/>`；
`m:f` 含 `<m:fPr/>`；settings.xml 含 `m:mathPr`/`m:mathFont=Cambria Math`。
手写 OMML 若缺上述空元素与根声明，Word 可能拒开或按纯文本渲染——所以**一律走 doc_insert_math，不手写**。
