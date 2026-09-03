# 辅助视觉模型配置（Qwen-VL @ DashScope）

## 背景

能源审计中的图片识别场景（设备铭牌、仪表读数、建筑图纸）多为中文内容。DeepSeek 不支持原生视觉输入，因此需要配置辅助视觉模型。

## 推荐方案：Qwen-VL Max（DashScope 国内端点）

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:
    provider: alibaba          # DashScope（阿里云百炼）
    model: qwen-vl-max         # Qwen-VL Max
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 链路对比

| | 之前 | 现在 |
|------|------|------|
| 主模型 | DeepSeek（跳过） | DeepSeek（跳过） |
| fallback | OpenRouter Gemini Flash | Qwen-VL Max（直连 DashScope） |
| 语言 | 英文主导 | 中文原生 |
| 铭牌/仪表 | 通用描述，不懂"COP"、"定额" | 领域理解力强 |

## 验证

```bash
# 测试 Qwen-VL 视觉（需要实际图片）
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-vl-max","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}},{"type":"text","text":"描述这张图片"}]}]}'
```

## 环境变量

- `DASHSCOPE_API_KEY` — 必需，阿里云百炼 API Key
- Key 同时用于 RAG embedding（Qwen text-embedding-v3）

## Pitfalls

1. **Hermes 优先读 config.yaml**：仅设 `AUXILIARY_VISION_MODEL` 环境变量不够，会被 config 覆盖。
2. **provider 别名**：`alibaba` = `dashscope` = `alibaba-cloud` = `qwen-dashscope`
3. **端点**：中国用户用 `dashscope.aliyuncs.com`，国际用户用 `dashscope-intl.aliyuncs.com`
