---
title: ONLYOFFICE 接入指南

---

# ONLYOFFICE 接入指南

本文档是一份**可照着抄**的接入教程：从部署 Document Server 开始，到后端实现（签名、下载、保存回调），再到 Vue 前端嵌入，最后是安全要点与常见坑。文中的后端实现与前端架构，是一套经过 E2E 验证的完整闭环。

## 1. 你必须要先理解的架构

ONLYOFFICE 的集成是**三方通信**模型，这决定了后面所有代码的形态：

```
┌──────────────── 你的应用 ────────────────┐
│                                         │
│  前端页面（Vue/React/iframe shell）       │
│    │ ① 加载 <DS>/api.js                  │
│    │ ② 拿 config（document.url / callbackUrl / token）
│    │ ③ new DocsAPI.DocEditor(el, config)│
│    ▼                                    │
│  你的后端（存文件 + 签名 + 收回调）        │
│    ├─ GET  /download?file_id=  ←─ ⑤ DS 拉文件
│    └─ POST /save               ←─ ⑦ DS 回传保存
└───────────────┬────────────────────────┘
                │ ④ iframe 嵌入 / 同源代理
          ┌─────▼─────┐
          │ Document  │ ⑥ 编辑器内编辑
          │  Server   │
          └───────────┘
```

三个铁律：

1. **Document Server 必须能直接访问你的两个 URL**：`document.url`（拉取原始文件）和 `editorConfig.callbackUrl`（回传保存结果）。这俩地址必须写**DS 能访问到的地址**（如 `http://192.168.x.x:39250/...`），不能是浏览器用的 `localhost`。
2. **JWT 密钥两端一致**：DS 的 `JWT_SECRET` 必须等于你后端签名用的密钥，否则 DS 会拒收 config（错误提示 `Invalid token`）。
3. **`document.key` 必须唯一且保存后轮换**：key 是 DS 的缓存键。同一个 key 打开同一个文档，DS 不会重新拉取你的文件；保存回调后若不换 key，再打开会读到旧内容。

## 2. 部署 Document Server

### 2.1 Docker 安装（含 JWT 与中文字体）

```bash
# 生成一个强随机密钥，两处都要用
SECRET=$(openssl rand -base64 32)

docker run -i -t -d -p 8090:80 --restart=always \
  -e JWT_ENABLED=true \
  -e JWT_SECRET="$SECRET" \
  -v onlyoffice_data:/var/www/onlyoffice/Data \
  -v /opt/onlyoffice/fonts:/usr/share/fonts/onlyoffice:ro \
  --name onlyoffice-documentserver \
  onlyoffice/documentserver:latest
```

| 参数 | 含义 |
|---|---|
| `-p 8090:80` | DS 对外端口（示例 8090，可改） |
| `JWT_ENABLED=true` `JWT_SECRET=...` | 开启并配置共享密钥（HS256） |
| `onlyoffice_data:/var/www/onlyoffice/Data` | 持久化数据卷（DS 的临时文件、转换缓存） |
| `/opt/onlyoffice/fonts:/usr/share/fonts/onlyoffice:ro` | **中文字体挂载**，不挂的话中文/生僻字渲染成方框 |
| `--restart=always` | 崩溃自动拉起 |

> 字体目录里至少要放 `msyh.ttc`（微软雅黑）、`simsun.ttc`（宋体）、`simhei.ttf`（黑体）等常用字体。字体只在容器启动时扫描，挂载后要 `docker restart onlyoffice-documentserver`。

### 2.2 验证部署

```bash
# 健康检查（容器内自检，会跑几十秒）
curl http://<DS_HOST>:8090/healthcheck
# 期望输出: {"status":true}

# 前端 API 入口可访问
curl -I http://<DS_HOST>:8090/web-apps/apps/api/documents/api.js
```

### 2.3 最关键的一步：连通性自检

装完先做一次**三机联通测试**（你的应用服务器 → DS、DS → 你的应用服务器），这一步能避免后面 90% 的"打不开/存不上"问题：

```bash
# 在【应用服务器】上测：能到 DS
curl -s http://<DS_HOST>:8090/healthcheck

# 在【DS 服务器上】测：DS 能回到你的应用
curl -s http://<YOUR_APP_IP>:<YOUR_PORT>/some-ping-endpoint
```

如果 DS 与你的应用不在同一网段/被防火墙隔离，需要把 `document.url` 和 `callbackUrl` 写成 DS 可达的内网地址（本仓库做法：桌面应用监听 `0.0.0.0:39250`，回调地址写 `http://192.168.0.238:39250`，DS 侧网络可达该 IP）。

## 3. 后端接入（核心工作量在这里）

后端要提供 4 个能力：**生成签名 config、文件下载、保存回调、强制保存**。以下代码是仓库 `tools/office_onlyoffice.py` 的简化版，可直接照抄改造。

### 3.1 配置与注册表

```python
import json, os, re, secrets, time, hmac, hashlib, base64, threading, urllib.request, urllib.parse
from pathlib import Path

# ---- 环境配置 ----
DS_URL        = os.environ["HERMES_OFFICE_DS_URL"]        # http://<DS_HOST>:8090
JWT_SECRET    = os.environ["HERMES_OFFICE_JWT_SECRET"]    # 与 DS 的 JWT_SECRET 一致
CALLBACK_HOST = os.environ.get("HERMES_OFFICE_CALLBACK_HOST", "")  # DS 可达的应用 IP
PREVIEW_PORT  = int(os.environ.get("HERMES_OFFICE_PREVIEW_PORT", "39250"))

def public_base() -> str:
    """DS 侧可达的应用基址（回调与下载都基于它拼 URL）"""
    return f"http://{CALLBACK_HOST}:{PREVIEW_PORT}"

# ---- 文档注册表：file_id ↔ 磁盘路径 ↔ key ----
_registry = {}          # file_id -> {"path": Path, "key": str, "title": str, "last_status": int}
_registry_lock = threading.Lock()

def register_file(path: Path, title: str) -> str:
    """打开文档前注册，返回 file_id。key 每次打开都重新生成。"""
    file_id = secrets.token_hex(8)
    with _registry_lock:
        _registry[file_id] = {
            "path": path, "key": f"k-{int(time.time()*1000)}-{secrets.token_hex(4)}",
            "title": title, "last_status": 0,
        }
    return file_id

def rotate_key(file_id: str) -> None:
    """保存后必须轮换 key，否则 DS 缓存旧内容"""
    with _registry_lock:
        e = _registry.get(file_id)
        if e:
            e["key"] = f"k-{int(time.time()*1000)}-{secrets.token_hex(4)}"
```

### 3.2 JWT 签名（HS256，纯标准库实现）

```python
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def sign_token(payload: dict, *, ttl: int | None = 3600) -> str:
    """对 payload 做 HS256 签名。config 用 ttl=3600，下载链接用短 ttl。"""
    if ttl:
        payload = {**payload, "exp": int(time.time()) + ttl}
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body   = _b64(json.dumps(payload).encode())
    sig    = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"

def verify_token(token: str) -> dict | None:
    """验签 + 过期校验。任何一步失败返回 None。"""
    try:
        header, body, sig = token.split(".")
        expect = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
```

> 用标准库 `hmac` 而不是 `jwt` 库，少一个依赖；生产环境用成熟的 `PyJWT` 也行，但**务必用 `compare_digest` 做常量时间比较**，防止时序攻击。

### 3.3 生成编辑器 config（前端拿这个渲染编辑器）

```python
def make_editor_config(file_id: str) -> dict:
    with _registry_lock:
        e = _registry[file_id]
    base = public_base()
    # document.url：DS 去拉文件，必须 DS 可达；加短签名 token 防盗链
    download_url = f"{base}/api/onlyoffice/download?file_id={file_id}&token=" + \
                   sign_token({"file_id": file_id, "scope": "download"}, ttl=300)
    # callbackUrl：DS 保存时回传，加服务端保存的密钥校验
    callback_url = f"{base}/api/onlyoffice/save"

    config = {
        "type": "desktop",
        "documentType": file_type_of(e["path"]),          # "word" | "cell" | "slide"
        "document": {
            "fileType": e["path"].suffix.lstrip("."),     # "docx" | "xlsx" | "pptx"
            "key": e["key"],
            "title": e["title"],
            "url": download_url,
            "permissions": {"edit": True, "download": True},
        },
        "editorConfig": {
            "callbackUrl": callback_url,
            "lang": "zh-CN",
            "mode": "edit",
            "customization": {
                "forcesave": True,          # 点保存立即触发回调，否则要等自动保存
                "autosave": True,
                "compactToolbar": False,
            },
            "user": {"name": "当前用户", "id": "user-1"},
            "coediting": "strict",
        },
        "events": {
            "onDocumentReady": {"handler": "onDocumentReady"},   # 对应前端事件回调
            "onDocumentStateChange": {"handler": "onDocumentStateChange"},
            "onError": {"handler": "onEditorError"},
        },
    }
    # 整个 config 签名后作为 token 字段：DS 会先验 token 再执行
    config["token"] = sign_token(config, ttl=3600)
    return config

def file_type_of(path: Path) -> str:
    s = path.suffix.lower()
    if s in (".docx", ".doc", ".odt", ".rtf", ".txt"): return "word"
    if s in (".xlsx", ".xls", ".ods", ".csv"):         return "cell"
    if s in (".pptx", ".ppt", ".odp"):                 return "slide"
    raise ValueError(f"unsupported office type: {s}")
```

**为什么 config 要整体签名？** DS 收到 config 后会验 `token` 字段（用同一个 `JWT_SECRET`）。攻击者如果篡改 `document.url` 指向自己的服务器，DS 就会把文件发给攻击者；签名挡住了这个攻击面。

### 3.4 下载端点（DS 拉取原始文件）

```python
# GET /api/onlyoffice/download?file_id=xxx&token=xxx
def handle_download(params: dict):
    file_id = params.get("file_id", "")
    token   = params.get("token", "")
    payload = verify_token(token)                 # 查询参数里的短签名 token
    if not payload or payload.get("file_id") != file_id or payload.get("scope") != "download":
        return 403, "forbidden"
    with _registry_lock:
        path = _registry[file_id]["path"]
    return 200, path.read_bytes(), {"Content-Type": "application/octet-stream"}
```

### 3.5 保存回调端点（DS 回传编辑结果）——整个集成最核心的端点

```python
# POST /api/onlyoffice/save
# 请求头: Authorization: Bearer <jwt>   ← DS 用 JWT_SECRET 对回调 body 签名
# 请求体: {"status": 2, "url": "...", "key": "...", "users": [...], ...}
def handle_save_callback(headers: dict, body: dict) -> dict:
    # 1) 验签：区分回调 token 与 config token（见 5.2 节）
    auth = headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    payload = verify_callback_token(token, body)   # 必须单独实现，不能复用 config 验签
    if not payload:
        return 403, {"error": 1}

    status = body.get("status", 0)
    file_id = payload.get("file_id")
    with _registry_lock:
        e = _registry[file_id]
        e["last_status"] = status

    if status in (2, 6):          # 2=可保存, 6=强制保存
        save_url = body.get("url", "")
        if not re.match(r"^https?://", save_url):
            return 400, {"error": 1}
        # 2) 从 DS 的 url 下载最新字节
        req = urllib.request.Request(save_url, headers={"Authorization": f"Bearer {JWT_SECRET}"})
        data = urllib.request.urlopen(req, timeout=60).read()
        # 3) 原子写盘：先写临时文件再 replace，防止写一半崩溃损坏原文件
        tmp = e["path"].with_suffix(e["path"].suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(e["path"])
        # 4) key 轮换（铁律 3）
        rotate_key(file_id)
        return 200, {"error": 0}

    if status in (1, 4):          # 1=编辑中, 4=关闭无改动
        rotate_key(file_id)       # 无改动也要轮换，避免缓存陈旧
        return 200, {"error": 0}
    if status in (3, 7):          # 3=保存出错, 7=强制保存出错
        return 200, {"error": 0}  # 记日志即可，不要返回非 200（DS 会重试风暴）
    return 200, {"error": 0}
```

回调状态码速查表（**必须背下来**）：

| status | 含义 | 你的处理 |
|---|---|---|
| `1` | 正在编辑（打开/重开） | 轮换 key |
| `2` | **保存就绪** | 下载 `body.url` → 原子写盘 → 轮换 key |
| `3` | 保存出错 | 记日志 |
| `4` | 关闭且无改动 | 轮换 key |
| `6` | **强制保存** | 同 status 2，写盘 + 轮换 key |
| `7` | 强制保存出错 | 记日志 |

### 3.6 强制保存（Command Service）

ONLYOFFICE 9.x 之后，前端调用 `mc:forceSave` **不会再触发回调**，必须在服务端主动让 DS 落盘：

```python
# POST <DS>/command
def request_forcesave(file_id: str) -> None:
    with _registry_lock:
        key = _registry[file_id]["key"]
    body = {"c": "forcesave", "key": key}
    req = urllib.request.Request(
        f"{DS_URL}/command",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {JWT_SECRET}"},
    )
    urllib.request.urlopen(req, timeout=10)   # DS 落盘后会自动回调你的 /save（status 6）
```

> 同类的 command 还有 `getstatus`（查询文档当前状态）和 `drop`（强制断开连接）。

### 3.7 转换 API（无 Office 环境下的 PDF 预览/导出）

```python
# POST <DS>/converter
def convert_to_pdf(src_path: Path, dst_path: Path) -> None:
    with _registry_lock:
        pass  # 转换用独立 key，避免与编辑会话互踩
    key = f"conv-{int(time.time()*1000)}"
    base = public_base()
    body = {
        "url": f"{base}/api/onlyoffice/download?file_id={src_id}&token={...}",  # DS 可下载的源文件
        "filetype": src_path.suffix.lstrip("."),
        "outputtype": "pdf",
        "key": key,
        "title": src_path.name,
        "async": False,               # 同步等结果
    }
    req = urllib.request.Request(f"{DS_URL}/converter",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {JWT_SECRET}"})
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    if resp.get("endConvert") and resp.get("fileUrl"):
        urllib.request.urlretrieve(resp["fileUrl"], dst_path)
    else:
        raise RuntimeError(f"conversion failed: {resp.get('error')}")
```

### 3.8 一个额外的安全动作：限制 `file_id` 不能是路径穿越

`file_id` 是自己生成的随机 hex，天然安全；但如果你的系统允许外部传入路径，**绝对不要**让 `download`/`save` 端点接受任意路径字符串，只接受注册表里的 `file_id`（这也是为什么必须有注册表这层间接）。

## 4. 前端接入（Vue）

有两种方式，按需选择：

### 方式 A：官方 Vue 组件 `@onlyoffice/document-editor-vue`（最快）

```bash
npm install @onlyoffice/document-editor-vue
```

```vue
<!-- Editor.vue -->
<script setup>
import { DocumentEditor } from '@onlyoffice/document-editor-vue'
import { ref, onMounted } from 'vue'

const config = ref(null)
const documentServerUrl = ref('http://<DS_HOST>:8090')   // 不含末尾斜杠

const handleReady = () => console.log('编辑器就绪')
const handleStateChange = (e) => console.log('编辑状态:', e.data)
const handleError = (e) => console.error('编辑器错误:', e.data)

onMounted(async () => {
  // 从你自己的后端拿签名 config
  const res = await fetch('/api/onlyoffice/config?file_id=' + fileId)
  config.value = await res.json()
})
</script>

<template>
  <div v-if="config" style="width: 100%; height: 100%">
    <DocumentEditor
      id="docxEditor"
      :documentServerUrl="documentServerUrl"
      :config="config"
      @document-ready="handleReady"
      @document-state-change="handleStateChange"
      @error="handleError"
    />
  </div>
</template>
```

> 组件本质是封装了"动态加载 api.js + `new DocsAPI.DocEditor()`"。注意 `documentServerUrl` 是给**浏览器**加载 api.js 的（可写公网地址），而 config 里的 `document.url`/`callbackUrl` 是给 **DS** 用的（必须 DS 可达），两者不是一回事。

### 方式 B：手动 iframe shell + DocsAPI（可控性最高，本仓库用这种）

本仓库的做法是把编辑器封装成一个**同源 iframe shell**（`/onlyoffice` 页面），而不是直接在主页面里塞编辑器。好处：编辑器与主应用隔离、可自定义 UI、无跨域问题。

```html
<!-- public/onlyoffice.html —— 由你的后端预览服务器托管，或任意静态服务 -->
<!DOCTYPE html>
<html>
<head>
  <script src="http://<DS_HOST>:8090/web-apps/apps/api/documents/api.js"></script>
</head>
<body style="margin:0">
  <div id="placeholder"></div>
  <script>
    const params = new URLSearchParams(location.search);
    const fileId = params.get('file_id');

    // 1) 从后端拿签名 config
    fetch(`/api/onlyoffice/config?file_id=${fileId}`)
      .then(r => r.json())
      .then(config => {
        // 2) 渲染编辑器
        const editor = new DocsAPI.DocEditor('placeholder', {
          ...config,
          events: {
            onDocumentReady:   () => parent.postMessage({ type: 'office-ready' }, '*'),
            onDocumentStateChange: (e) => parent.postMessage(
              { type: 'office-state-change', data: e.data }, '*'),
            onError:           (e) => parent.postMessage({ type: 'office-error', data: e.data }, '*'),
            onRequestSaveAs:   () => editor.executeCommand('mc:saveAs', { title: '导出' }),
          }
        });

        // 3) 接收父页面指令（如：强制保存、选中文本给 AI 分析）
        window.addEventListener('message', (ev) => {
          if (ev.data?.type === 'office-command') {
            editor.executeCommand(ev.data.cmd, ev.data.args);
          }
        });
      });
  </script>
</body>
</html>
```

主应用（Vue）只需一个 iframe：

```vue
<template>
  <iframe
    :src="`http://127.0.0.1:${previewPort}/onlyoffice?file_id=${fileId}`"
    style="width:100%;height:100%;border:0"
    @load="onLoad"
  />
</template>
<script setup>
import { onMounted, onBeforeUnmount } from 'vue'

const onMessage = (ev) => {
  switch (ev.data?.type) {
    case 'office-ready':       /* 编辑器就绪，可以启用保存按钮 */ break
    case 'office-state-change': /* ev.data.data === true 表示有未保存改动 */ break
    case 'office-error':       /* 显示错误 */ break
  }
}

const forceSave = () => {
  // 方式1（新版 DS 推荐）：走后端 command service 强制落盘
  fetch('/api/onlyoffice/force-save', { method: 'POST', body: JSON.stringify({ file_id: fileId }) })
  // 方式2（旧版可用）：给 iframe 发命令
  // iframeRef.value.contentWindow.postMessage({ type: 'office-command', cmd: 'mc:forceSave' }, '*')
}

onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))
</script>
```

### 前端必须处理的 4 个信号

| 事件 | 触发时机 | 你的动作 |
|---|---|---|
| `onDocumentReady` | 编辑器加载完 | 启用工具栏的"保存"按钮 |
| `onDocumentStateChange` | 有无未保存改动 | `true` 时提示用户"有未保存更改" |
| `onError` | 任何错误 | 弹错误提示（常见 `-4` token 无效） |
| 保存回调（后端） | DS 落盘 | 通过轮询 `/api/onlyoffice/status` 刷新 UI |

## 5. 完整时序（打开 → 编辑 → 保存 → 强制保存）

```
浏览器/Vue                 你的后端                 Document Server
   │                          │                          │
   │ ① iframe shell 加载      │                          │
   │ ──GET /onlyoffice?file_id=→                          │
   │                          │                          │
   │ ② fetch config           │                          │
   │ ──GET /api/onlyoffice/config──→ 生成签名 config      │
   │ ←──── config(token) ──────                          │
   │                          │                          │
   │ ③ 加载 api.js ────────────────────────────────────→ │
   │ ④ new DocsAPI.DocEditor  │                          │
   │ ─────────── config ────────────────────────────────→ │ 验 token ✓
   │                          │ ⑤ GET /download?file_id= │ ←── 拉取原始文件
   │                          │ ←────── 文件字节 ──────── │
   │ ⑥ 用户编辑中...          │                          │
   │                          │ ⑦ POST /save (status 1)  │ ←── 打开回调
   │                          │ ←──── {"error":0} ─────── │
   │ ⑧ 用户点保存/自动保存    │                          │
   │                          │ ⑨ POST /save (status 2)  │ ←── 保存回调
   │                          │   下载 body.url → 写盘    │
   │                          │   rotate key              │
   │                          │ ←──── {"error":0} ─────── │
   │                          │                          │
   │ ⑩ 强制保存（可选）       │                          │
   │ ──POST /api/onlyoffice/force-save──→ POST /command   │
   │                          │ ──── forcesave ──────────→│
   │                          │ ←──── POST /save (6) ─────│ ←── 强制保存回调
```

## 6. 安全要点（每条都踩过坑）

### 6.1 必须校验 JWT
- **config token**：签名整个 config，`document.url`/`callbackUrl` 都在签名内，防篡改。
- **回调 token**：DS 请求 `callbackUrl` 时带 `Authorization: Bearer <token>`，token 的 payload 是**回调 body 本身**。验签时必须**重新对收到的 body 计算签名比对**，防止重放攻击。
- **下载 token**：query 参数里放短 ttl（300s）签名 token，防别人拿你的下载链接乱拉文件。

### 6.2 config token 与回调 token 必须分开验
回调 `Authorization` 头里的 token 其 payload 是回调 body；config 里的 `token` 字段其 payload 是整个 config。**两者结构不同，验签函数必须分开实现**，否则攻击者把 config token 塞进回调 Authorization 头就能绕过认证（本仓库专门用 `check_callback_auth()` 区分，并额外校验 `body.url` 不是指向内网的地址）。

### 6.3 保存写盘必须原子
```python
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_bytes(data)
tmp.replace(path)          # 同目录 replace 是原子的（POSIX 与 Windows NTFS 均如此）
```
直接 `path.write_bytes(data)` 在写一半崩溃时会把原文件写坏。

### 6.4 回调返回非 200 会导致重试风暴
DS 对回调失败的响应会**指数退避重试**。除鉴权失败外，一律返回 `200 {"error": 0}`；业务失败（写盘失败）记日志 + 返回 `{"error": 1}` 但 HTTP 仍 200。

### 6.5 `body.url` 校验
回调里 `body.url` 是 DS 给的文件下载地址，**必须校验是 http(s) 且不能指向内网地址**（防 SSRF：攻击者构造回调把 url 指向内网 IP，你的服务器就会去请求内网服务）。

## 7. 常见坑速查表

| 症状 | 原因 | 解决 |
|---|---|---|
| 打开白屏，控制台报 `-4 Invalid token` | JWT 密钥不一致 或 config 没签名 | 核对 DS `JWT_SECRET` 与后端一致；给 config 加 `token` |
| 编辑器提示"无法下载文档" | DS 访问不到 `document.url` | `document.url` 改用 DS 可达的内网地址；测试 DS 服务器 curl 该地址 |
| 点保存没反应/改了不落盘 | 没配 `callbackUrl` 或 DS 到不了回调地址 | 配 `editorConfig.callbackUrl`；在 DS 服务器 curl 回调地址 |
| 保存要等 10 分钟才生效 | 没开 `forcesave`，等自动保存 | `customization.forcesave: true`；主动调用 command `forcesave` |
| 改了文件再打开还是旧内容 | 没轮换 key | status 1/2/4/6 回调后 `rotate_key()` |
| 中文显示成方框 | 容器缺中文字体 | 挂载字体目录 + `docker restart` |
| 同一文档多人编辑互相覆盖 | `coediting` 配置不当 | `editorConfig.coediting: "strict"` |
| 本地能开、线上打不开 | 浏览器地址与 DS 地址跨域 | iframe shell 同源托管 api.js 地址用公网地址，config 用 DS 可达地址 |
| 强制保存按钮无效 | 9.x 后 `mc:forceSave` 不触发回调 | 改用服务端 `/command` 的 `forcesave` |

## 8. 验证清单（接入完成后逐项过）

- [ ] `curl http://<DS_HOST>:8090/healthcheck` 返回 `{"status":true}`
- [ ] 浏览器能打开编辑器（`onDocumentReady` 触发）
- [ ] 编辑文字 → 点保存 → **文件在磁盘上真的变了**（用记事本/解压检查 docx 内容）
- [ ] 关闭再打开，看到的是保存后的内容（key 轮换生效）
- [ ] 去掉 `Authorization` 头访问 `/save`，返回 403（鉴权生效）
- [ ] 伪造 config token 访问编辑器，DS 拒绝（签名生效）
- [ ] 改文件后强制保存，文件内容更新（forcesave 生效）
- [ ] 无 Office 环境：docx/xlsx/pptx 能转 PDF（converter 生效）
- [ ] 中文标题/内容渲染正常（字体生效）

自动化验证可参照仓库的 `tests/tools/e2e_onlyoffice_ds.mjs`：用 Playwright 打开真实 DS 页面 → 输入文字 → Ctrl+S → 断言磁盘文件内容变化，整个链路（浏览器 → 你的后端 → DS → 落盘）一次验证。

## 9. 仓库参考实现（照抄时先看这些文件）

| 文件 | 内容 |
|---|---|
| `scripts/onlyoffice-ds-setup.sh` | DS 部署脚本（Docker 参数、JWT、字体、卷） |
| `tools/office_onlyoffice.py` | JWT 签名、config 生成、download/save 端点、command 转发 |
| `tools/office_preview_server.py` | 预览服务器、`/onlyoffice` embed shell、同源代理 |
| `tools/office_preview_api.py` | 引擎选择（DS → 本地 SDK → officecli 三级回退） |
| `tools/office_editor_tool.py` | 暴露给 Agent 的编辑工具 |
| `tools/office_sdk_manager.py` | ONLYOFFICE 桌面 SDK 管理 |
| `apps/desktop/src/components/chat/office-preview.tsx` | 前端预览组件（iframe + 回退渲染） |
| `apps/desktop/src/app/settings/onlyoffice-settings.tsx` | 连接配置 UI |
| `tests/tools/e2e_onlyoffice_ds.mjs` | 真实 DS E2E 验证 |

**环境变量约定**（本仓库）：`HERMES_OFFICE_DS_URL`、`HERMES_OFFICE_JWT_SECRET`、`HERMES_OFFICE_CALLBACK_HOST`、`HERMES_OFFICE_PREVIEW_PORT` —— 前两个同时设置即启用远程 DS 编辑，未设置时回退到本地 SDK 只读预览。