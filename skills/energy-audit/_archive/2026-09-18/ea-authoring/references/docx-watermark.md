# 报告 docx 水印（OnlyOffice 兼容）

SOUL 红线：落盘前必须有文字水印，内容为被审计单位名称；无水印视为未完成交付。

本文件只回答三件事：**何时加、加在哪、怎么加才兼容 OnlyOffice**。

---

## 何时加

- **一次、全文写完之后、第一次正式 `office_save` 之后立刻做。**
- 不要在第 1～8 章写作过程中反复加。
- 不要在封面/目录写完就加（后续 `office_edit` 可能重建节/页眉，水印会被冲掉）。
- 打开已有报告补交时：若页眉没有 DrawingML 水印，补加后再 `office_save`。

推荐顺序：

```
office_create → 逐章 office_edit → office_save 到交付路径
  → office_cli_command 正文首行缩进 2 字符（见 docx-first-line-indent.md）
  → execute_code 给该 .docx 注入水印（原地覆盖）
  → office_preview / 抽查 header*.xml
```

`office_editor` **没有**水印 MCP 操作，不要用 `office_edit` 往正文插入灰色大字冒充水印。

---

## 加在哪

| 项 | 规定 |
|----|------|
| 位置 | **每个节的页眉**（`section.header`；若启用首页不同/奇偶页不同，还要写 `first_page_header`、`even_page_header`） |
| OOXML | 页眉里的 **DrawingML** `w:drawing` → `wp:anchor behindDoc="1"`（衬于文字下、页面水平/垂直居中） |
| 文案 | `proj.base.unit_name`（被审计单位全称）。**不要用** `proj.base.name`（带「能源审计」后缀） |
| 空值 | `unit_name` 为空时用任务里的项目名称；再没有则停下来补数据，禁止写「WATERMARK」占位 |
| 外观 | 浅灰 `#C0C0C0`、宋体、斜向约 45°、半透明观感靠浅色实现；不挡正文阅读 |

覆盖范围：封面、目录、正文所有页。页眉注入一次即可随节应用到各页。

---

## 怎么加才兼容 OnlyOffice

OnlyOffice 对 Word 经典水印（VML WordArt）支持差：导入常不显示，再保存会把 Word/WPS 里的水印弄丢。

| 做法 | Word | OnlyOffice | WPS | 结论 |
|------|------|------------|-----|------|
| VML `w:pict` + `v:shape` + `v:textpath` | 设计→水印的默认形态 | 经常不显示 | 往返易错 | **禁止** |
| DrawingML 页眉形状/文本框（`wp:anchor` + `wps:wsp`） | 能显示 | 一般能显示 | 一般能显示 | **默认采用** |
| DrawingML 页眉图片（浅色斜字 PNG） | 稳 | 最稳 | 稳 | 文本框在 OO 仍看不见时的回退 |
| OnlyOffice `InsertWatermark` / `watermark_on_draw` | 不保证写进 docx | 仅 OO 会话 | — | author 不用（走 office_editor，不是 OO API） |
| 正文灰色大字 | 会占排版 | 能看见但不是水印 | 会破坏格式 | **禁止** |

硬规则：

1. 禁止生成或保留 `v:textpath` / `v:shapetype` 水印。
2. 必须写入 `word/header*.xml` 的 `w:drawing`，且 `behindDoc="1"`。
3. 不要依赖 Word「设计 → 水印」菜单语义；OnlyOffice 的「删除水印」也识别不到这种对象，这是预期。

---

## 实现（execute_code + python-docx）

对已经 `office_save` 的交付文件原地写入。`unit_name` 含 `& < >` 时必须 XML 转义。

```python
import html
from pathlib import Path
from docx import Document
from docx.oxml import parse_xml

def _watermark_paragraph_xml(text: str, doc_pr_id: int) -> str:
    safe = html.escape(text, quote=True)
    size = "88" if len(text) <= 12 else "56"  # 半磅：88=44pt
    return f'''
<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
     xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
     xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
  <w:r>
    <w:drawing>
      <wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"
                 relativeHeight="251658240" behindDoc="1" locked="0"
                 layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="page"><wp:align>center</wp:align></wp:positionH>
        <wp:positionV relativeFrom="page"><wp:align>center</wp:align></wp:positionV>
        <wp:extent cx="5486400" cy="2194560"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:wrapNone/>
        <wp:docPr id="{doc_pr_id}" name="EAWatermark"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
            <wps:wsp>
              <wps:cNvSpPr txBox="1"/>
              <wps:spPr>
                <a:xfrm rot="2700000">
                  <a:off x="0" y="0"/>
                  <a:ext cx="5486400" cy="2194560"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                <a:noFill/>
                <a:ln><a:noFill/></a:ln>
              </wps:spPr>
              <wps:txbx>
                <w:txbxContent>
                  <w:p>
                    <w:pPr><w:jc w:val="center"/></w:pPr>
                    <w:r>
                      <w:rPr>
                        <w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/>
                        <w:sz w:val="{size}"/>
                        <w:szCs w:val="{size}"/>
                        <w:color w:val="C0C0C0"/>
                      </w:rPr>
                      <w:t>{safe}</w:t>
                    </w:r>
                  </w:p>
                </w:txbxContent>
              </wps:txbx>
              <wps:bodyPr wrap="none" fromWordArt="0"><a:noAutofit/></wps:bodyPr>
            </wps:wsp>
          </a:graphicData>
        </a:graphic>
      </wp:anchor>
    </w:drawing>
  </w:r>
</w:p>'''

def add_unit_name_watermark(docx_path: str, unit_name: str) -> None:
    if not (unit_name or "").strip():
        raise ValueError("水印文案为空：需要 proj.base.unit_name")
    doc = Document(docx_path)
    n = 1
    for section in doc.sections:
        headers = [section.header]
        if section.different_first_page_header_footer:
            headers.append(section.first_page_header)
        if section.even_page_header is not None:
            headers.append(section.even_page_header)
        for header in headers:
            xml = header._element.xml
            if "EAWatermark" in xml or 'name="Watermark"' in xml:
                if "v:textpath" in xml:
                    raise RuntimeError("页眉含 VML textpath，禁止交付；改为 DrawingML 后重试")
                continue
            header._element.append(parse_xml(_watermark_paragraph_xml(unit_name.strip(), n)))
            n += 1
    doc.save(docx_path)

# add_unit_name_watermark(r"<交付路径>", proj.base.unit_name)
```

若 OnlyOffice 预览仍看不见：用 PIL 把同一文案做成浅灰斜字透明 PNG，再作为 DrawingML **图片**插入同一页眉位置（仍禁止 VML）。

---

## 验收

落盘后抽查（可用 `zipfile` 读包，不必 Word）：

1. `word/header*.xml` 中有 `w:drawing` 且 `behindDoc="1"`。
2. 全包内 **没有** `v:textpath`。
3. 水印字符串等于 `proj.base.unit_name`，不是 `proj.base.name`。
4. `office_preview` 正文可正常阅读，水印在文字下方。

任一失败 = 未完成交付，修好后再交。
