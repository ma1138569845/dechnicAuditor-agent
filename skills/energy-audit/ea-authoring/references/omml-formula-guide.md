# Word 公式编辑指南（第5章指标公式）

> 第5章 5.3 各指标段需要呈现计算公式。本指南给出三种方案与选用规则。

## 方案选择（按优先级）

| 方案 | 适用 | 优缺点 |
|------|------|--------|
| **A. 文本公式**（推荐，与正式交付报告一致） | 全部指标段 | 简单稳妥、跨渲染器一致；非数学对象 |
| B. OfficeCLI LaTeX | 确需数学公式对象时 | 一行命令；依赖 OfficeCLI 二进制 |
| C. python-docx 手写 OMML | OfficeCLI 不可用时 | 可实现但 XML 冗长易错 |

**默认用方案 A**：烟台法院正式版报告全部采用"符号 + 中文定义"的文本公式行，
格式为：

```
Ejfgn——单位建筑面积非供暖能耗，单位为千克标准煤每平方米年，kgce/(m²·a)；
```

**不用**：Word 的"插入公式"图形对象（不可批处理、样式不可控）、
截图/图片公式（模糊、不可检索、格式校验不过）。

## 第5章公式清单（符号与正式版一致）

| 指标 | 公式 | 变量 |
|------|------|------|
| 单位建筑面积非供暖能耗 5.3.1 | Ejfgn = (E − Egn − Ejt) / M | E 综合能耗 kgce/a；Egn 供暖能耗；Ejt 交通能耗；M 建筑面积 m² |
| 常规用能系统单位建筑面积电耗 5.3.2 | Ejd = ED / M | ED 电量总和 kWh/a（已剔供暖电耗）；M 建筑面积 |
| 人均综合能耗 5.3.3 | Er = E / P | E 综合能耗 kgce/a；P 用能人数 p |
| 取水指标 5.3.4（标题与公式按机构类型自适应，DB37/T 4452-2021） | 机关(7)：Vuc = Vk / Np（m³/(人·a)）；高校(3)：Vu = Wu / Nu（Nu=统招生+留学生+0.5×教职工）；中小学/幼儿园(4)：Vs = Wu / Ns（Ns=非住宿生+2×住宿生+教职工）；医院(5)：Vz = Wz / ΣNi × 10³（L/(床·日)，ΣNi=全年实际开放床日数）；政务/场馆(6)：Vui = Vj / Nc × 1000（L/(m²·a)） | 变量定义见 core/references/standards-values.md；不对标：政务/场馆（4452 无面积定额） |
| 单位采暖建筑面积供暖能耗 5.3.5 | Egn_m2 = Egn / Mgn | Egn 供暖能耗 kgce/a；Mgn 采暖建筑面积 m² |

> 变量符号（Ejfgn/Ejd/Er/Vuc/Egnm + 取水按类型 Vuc/Vu/Vs/Vz/Vui）以正式报告与 DB37/T 4452-2021 为准（2026-09-05 用户确认对齐）；报告中的符号不可自行改名。

## 方案 A：文本公式写法（python-docx）

```python
from docx import Document
doc = Document()
# 公式行：段首变量符号（TNR 斜体可选）+ 全角破折号 + 中文定义
p = doc.add_paragraph()
r = p.add_run("Ejfgn")
r.italic = True          # 变量符号用斜体（与正式版一致）
r.font.name = "Times New Roman"
p.add_run("——单位建筑面积非供暖能耗，单位为千克标准煤每平方米年，kgce/(m²·a)；")
# 符号/中文部分保持正文宋体 12pt
```

格式要求：
- 变量符号：Times New Roman 斜体，不加粗
- 中文定义与单位：宋体 12pt（正文同款）
- 单位写法不加括号：`kgce/(m²·a)`（报告铁律：单位不加括号）
- 公式行前后空行，左对齐或居中（与正文模板一致即可）

## 方案 B：OfficeCLI equation 元素（⚠ 不支持分式，勿用于 5.3 公式）

officecli 的 equation 元素（`add ... --type equation --prop formula=`）只支持线性表达式与上下标（`x^2`/`E_gn`），
**不支持分式**（`\frac{...}{...}` 不解析、`/` 不会转成 m:f 分数线，实测 m:f=0）。
5.3 五个公式全部是分式结构，**必须走方案 C**；方案 B 只可用于无分式的简单式子。

```bash
# 仅限无分式场景（如正文中的简单变量说明）
officecli add report.docx /body --type equation --prop formula="E_gn" --prop mode=display
```

## 方案 C：zip+lxml 注入 OMML（5.3 分式公式的唯一可行路径，2026-09-05 定）

python-docx 无内置公式 API，officecli equation 不支持分式；5.3 五个公式**一律用仓库脚本注入**：

```bash
python skills/energy-audit/energy-audit-report/scripts/fix_chapter5_formulas.py <报告.docx> [--dry-run]
```

脚本定位 5.3 节文本公式段（含 `=` 的 Normal 段落），替换为正式报告同款 OMML（m:f 分式 + m:sSub 下标）。
若脚本不可用，手工构造 `m:oMath` XML（结构见下方附录模板，抄写时注意 namespace 前缀 `m`）。

OMML 结构要点：`m:oMath` > `m:r`（含 `w:rPr` + `m:t`）表示普通文本；
分数用 `m:f`（m:num/m:den），下标用 `m:sSub`（m:e 为基底、m:sub 为下标）。

## 附录：常见 OMML 片段

分式（Ejfgn = 分子/分母，下标 E 在 m:e、jfgn 在 m:sub，2026-09-05 按正式报告修正）：

```xml
<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <m:sSub>
    <m:e><m:r><m:t>E</m:t></m:r></m:e>
    <m:sub><m:r><m:t>jfgn</m:t></m:r></m:sub>
  </m:sSub>
  <m:r><m:t>=</m:t></m:r>
  <m:f>
    <m:num>
      <m:r><m:t>E−</m:t></m:r>
      <m:sSub>
        <m:e><m:r><m:t>E</m:t></m:r></m:e>
        <m:sub><m:r><m:t>gn</m:t></m:r></m:sub>
      </m:sSub>
      <m:r><m:t>−</m:t></m:r>
      <m:sSub>
        <m:e><m:r><m:t>E</m:t></m:r></m:e>
        <m:sub><m:r><m:t>jt</m:t></m:r></m:sub>
      </m:sSub>
    </m:num>
    <m:den><m:r><m:t>M</m:t></m:r></m:den>
  </m:f>
</m:oMath>
```

⚠ 旧模板错误（勿抄）：`<m:sSub><m:e>...` 中 E 写在 sSub 之外、`<m:sub><m:r><m:t></m:t></m:r></m:sub>` 空下标——会渲染成无下标的错误公式。正确结构：基底字符在 `m:e` 内、下标字符在 `m:sub` 内。

> 生成后必须用 docx 渲染校验（officecli render / Word 打开），确认公式未变成乱码或纯文本。
> 若渲染异常，退回方案 A（文本公式），不得交付未验证的 OMML。
