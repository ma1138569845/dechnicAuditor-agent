# 报告正文首行缩进（2 字符）

SOUL 红线：落盘后、加水印前，必须给**正文自然段**加上首行缩进 2 字符；无缩进视为未完成交付。

本文件只回答三件事：**何时设、给谁设、怎么设**。全程用 **office 工具**（`office_cli_command` / `office_edit`）。

---

## 何时设

- **一次、全文写完并第一次正式 `office_save` 之后立刻做，再加水印。**
- 写作过程中若用 officecli 插入正文，可当时带上缩进属性（见下「写作时」）；仍须在落盘后做一次全文核对，补漏段。
- 不要用两个全角空格、`\u3000\u3000` 或段首空格假装缩进。
- 打开已有报告补交时：用 `office_cli_command` 抽查正文段，没有 `firstLineChars=200` 就补设。

推荐顺序：

```
office_create → 逐章 office_edit（或 office_cli_command add）
  → office_save 到交付路径
  → office_cli_command：筛正文段并 set firstLineChars=200
  → 加水印（见 docx-watermark.md）
  → office_preview
```

---

## 给谁设 / 不给谁设

只处理**各章正文自然段**。不是文档里每一个段落。

| 类别 | 是否缩进 | 判定（看 `officecli get` 的 `text` / `style` / `format`） |
|------|----------|------|
| 各章叙述性正文 | **要** | 非空；`style` 不是 Heading/标题/TOC/List；非居中/右对齐 |
| H1 / H2 / H3 | 不要 | `style` 含 Heading/标题；或「第X章」；或 `1.1` / `1.1.1` 且加粗；或 `size` ≥ 14pt |
| 封面、目录标题 | 不要 | 居中；「能源审计报告」「目录」 |
| 表题、图注 | 不要 | `align=center`；文本以 `表2-1` / `图2-1` 开头 |
| 表格单元格 | 不要 | 路径在 `tbl` 下。只处理 `/body` 的直接子段落，不要 `query paragraph` 全表 |
| 无序列表（1.6 等） | 不要 | 文本以 `●` / `•` / `·` / `○` 开头，或已有 `hangingIndent` / `listStyle` |
| 空段、封面 spacer | 不要 | 无可见文本 |

换算（12pt 小四号）：

- 2 字符 = OOXML `w:ind @w:firstLineChars="200"`（百分之一字符）
- 回退长度：`firstLineIndent=24pt`（24pt = 2 × 12pt）

officecli 属性名（已核实）：

| 属性 | 值 | 说明 |
|------|----|------|
| `firstLineChars` | `200` | **主属性**，字符相对缩进 |
| `firstLineIndent` | `24pt` | 长度回退，与上一行一起设 |

---

## 怎么设（office 工具）

### 写作时（插入正文段）

**officecli 插入**（`office_cli_command`）：

```text
officecli add "<交付路径>" /body --type paragraph --prop text="……" --prop align=justify --prop lineSpacing=1.5x --prop size=12pt --prop font.ea=宋体 --prop font.latin="Times New Roman" --prop firstLineChars=200 --prop firstLineIndent=24pt
```

标题、表题、图注、列表 **不要**带 `firstLineChars`。

**`office_edit`（editor_sdk）插入**：`doc_insert_paragraph_with_text` 默认无首行缩进。插入时若 `office_list_tools` 能找到段落缩进参数就带上；**找不到不要用正文空格凑**。无论插段时带没带上，落盘后都必须走下面的全文补设。

### 落盘后全文补设（强制）

文件必须已经 `office_save` 到交付路径。全部命令走 **`office_cli_command`**（`command` 以 `officecli` 开头）。优先用稳定路径 `/body/p[@paraId=…]`，不要用会随插入漂移的 `/body/p[N]`。

**1. 列出正文级段落（不含单元格）**

```text
officecli get "<交付路径>" /body --depth 1 --json
```

只看 `type=paragraph` 的直接子节点。忽略 `type=table` / `type=section`。

**2. 按「给谁设」过滤**，得到要改的 `path` 列表。一条都没有 → 停止交付，检查判定。

**3. 批量写入**（推荐 `--input`，避免命令行转义）：

`indent-batch.json` 示例：

```json
[
  {
    "command": "set",
    "path": "/body/p[@paraId=00100002]",
    "props": {
      "firstLineChars": "200",
      "firstLineIndent": "24pt"
    }
  }
]
```

```text
officecli batch "<交付路径>" --input "<indent-batch.json 的绝对路径>" --json
officecli save "<交付路径>"
```

段数很少时可以逐条：

```text
officecli set "<交付路径>" "/body/p[@paraId=00100002]" --prop firstLineChars=200 --prop firstLineIndent=24pt --json
```

**4. 抽查**

```text
officecli get "<交付路径>" "/body/p[@paraId=<正文段>]" --json
```

`format.firstLineChars` 应为 `200`。再抽一条 H1/表题/列表，确认 **没有** `firstLineChars`。

---

## 验收

1. 抽 3 段各章叙述正文：`officecli get` 的 `format.firstLineChars` 为 `200`（可同时有 `firstLineIndent=24pt`）。
2. 抽 H1「第X章」、H2/H3、`表N-` / `图N-`、`● ` 列表、任一单元格：这些段落 **没有** 首行缩进。
3. 正文里没有段首全角空格冒充缩进。
4. `office_preview` 正文首行明显缩进约两字，标题仍顶格。

任一失败 = 未完成交付，修好后再交。
