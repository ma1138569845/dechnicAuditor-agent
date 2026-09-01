# 同类参考报告目录（已迁移）

仿写时**先按地区、再按类型**找参考报告：区县 → 地市 → 省份，然后才是审计类型
（公共机构 / 公共建筑 / 工业企业）和机构类别（法院、医院等，从文件名识别）。
同地区报告比外省同类型更有参考价值。

默认读取 Hermes RAG 数据目录（profile-aware）：

```
{HERMES_HOME}/rag/report/
  {省份}/{地市}/{区县}/{审计类型}/*.docx

  例:
  山东/烟台/经济技术开发区/公共机构/烟台经济技术开发区人民法院能源审计报告.docx
  山东/烟台/芝罘/公共机构/某机关能源审计报告.docx
  山东/青岛/市南/公共机构/某医院能源审计报告.docx
```

文件名已含地名时，即使未按目录分层也能匹配（如根目录下的
`烟台经济技术开发区人民法院能源审计报告.docx`）。

默认读取 Hermes RAG 数据目录（profile-aware）。**Windows 本机实际路径**是：

```
%LOCALAPPDATA%\hermes\rag\report\
```

即 `C:\Users\<用户>\AppData\Local\hermes\rag\report\`（不是 Linux 的 `~/.hermes`）。
Linux/macOS 才是 `~/.hermes/rag/report/`。若使用 profile，则为
`{HERMES_HOME}/profiles/<name>/rag/report/`。

支持 `.docx` / `.doc` / `.md` / `.txt`。

覆盖此路径的方式：

1. 环境变量 `EA_REFERENCE_DIR`
2. Hermes `config.yaml` → `energy_audit.imitate.reference_dir`
