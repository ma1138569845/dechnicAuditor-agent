# 仿写装配 · 格式实施注记

> **格式权威 = `energy-audit-core/references/report-format-spec.md`（唯一全文；本页不复制规则）。**
> 本页仅记仿写路径（`assemble_report.py` / `ReportGenerator`）的实施要点，供组装时快速对照；
> 如与 core 版冲突，一律以 core 版为准。

- **落实范围**：封面 / 基本信息表 / 目录标题 / 正文字体由 `scripts/assemble_report.py`（`ReportGenerator`）执行。
- **`能源审计基本信息表`**：由组装脚本写入，不要另起一套表。
- **目录域与单位名称水印**：组装落盘后写入；水印细则见 `scripts/add_watermark.py`（DrawingML、`behindDoc=1`、禁 VML）。
- **正文缩进**：本路径用 `ReportGenerator._add_body_text` 写正文，不要改用 `office_cli_command`。
- **维护约定**：本页只随仿写路径实施方式变更而更新；core 版更新时无需同步（规则不在本页）。
