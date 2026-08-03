# jiuge-canva

jiuge-canva 是一个本地 APINebula 图像工作台，提供三种使用入口：

- PC 浏览器可视化页面：生图、本地改图、URL 改图、批量任务和结果预览。
- CLI：适合脚本、PowerShell 和自动化生成。
- MCP Server：让 Codex 等 MCP 客户端直接调用生图与改图工具。

项目不包含手机端适配，也不提供 Electron、Tauri 等独立桌面客户端。Web 页面由本地 Node.js 服务提供，默认只监听 `127.0.0.1`。

## 支持的模型分组

| 预设 | APINebula 分组 | 默认模型 | 协议 | 专用 Skill |
| --- | --- | --- | --- | --- |
| `image2` | `gpt-image-2-1k` | `gpt-image-2` | Images API | `nebula-image2-1k` |
| `image2_4k` | `image2-4k` | `gpt-image-2-4k` | Images API | `nebula-image2-4k` |
| `nanobanana` | `nanobanana` | `gemini-3.1-flash-image` | Gemini `generateContent` | `nebula-nanobanana` |
| `grok` | `Grok` | `grok-imagine-image` | Chat Completions | `nebula-grok` |

参数和分组以 [APINebula 图片文档](https://docs.apinebula.ai/docs/advanced/image) 为依据。Adobe 分组不在当前项目中。

## 环境与依赖

### 必需环境

- Windows、macOS 或 Linux。
- Node.js 20 或更高版本。
- npm 10 或兼容版本。
- 与所选模型分组匹配的 APINebula API Key。

主项目运行不需要 Python、数据库、Docker、全局前端构建工具或原生图像处理库。只有直接运行独立 Skill ZIP 内的脚本时需要 Python 3.9+。

### 项目直接依赖

依赖已经写入 `package.json` 和 `package-lock.json`，执行 `npm ci` 即可完整安装，不要逐个手动安装。

| 依赖 | 用途 |
| --- | --- |
| `@modelcontextprotocol/sdk` | MCP Server 与 stdio transport |
| `zod` | MCP 工具参数校验 |
| `busboy` | Web 本地改图的 multipart 文件上传 |
| `form-data` | 向上游 Images Edit API 提交参考图 |
| `dotenv` | 加载本地 `.env` 配置 |
| `lucide` | Web 页面本地图标资源 |

## 安装

```powershell
git clone https://github.com/jiugeovo/jiuge-canva.git
cd jiuge-canva
npm ci
Copy-Item .env.example .env
```

开发时如果修改了依赖，使用：

```powershell
npm install
```

如果 npm 全局缓存没有写入权限：

```powershell
npm install --cache .\.npm-cache
```

可选：把三个命令链接到本机 npm 命令目录：

```powershell
npm link
jiuge-canva --help
jiuge-canva-web --help
```

`npm link` 后可直接使用：

- `jiuge-canva`：CLI。
- `jiuge-canva-web`：Web 服务。
- `jiuge-canva-mcp`：MCP Server。

旧的 `nebula-canvas*` 命令仍作为兼容别名保留；新配置请使用 `jiuge-canva*`。

## 配置

`.env` 示例：

```env
APINEBULA_API_KEY=your_api_key_here
APINEBULA_BASE_URL=https://img-api.apinebula.ai

JIUGE_CANVA_IMAGE2_MODEL=gpt-image-2
JIUGE_CANVA_IMAGE2_4K_MODEL=gpt-image-2-4k
JIUGE_CANVA_NANOBANANA_MODEL=gemini-3.1-flash-image
JIUGE_CANVA_GROK_MODEL=grok-imagine-image

JIUGE_CANVA_OUTPUT_DIR=./outputs
JIUGE_CANVA_TIMEOUT_MS=1800000
JIUGE_CANVA_WEB_HOST=127.0.0.1
JIUGE_CANVA_WEB_PORT=8787
```

注意：

- `APINEBULA_BASE_URL` 必须填写根地址，不要追加 `/v1`。
- `.env` 已被 Git 忽略，不要把真实 Key 写入源码、README 或提交记录。
- Web 页面可以直接设置 Base URL 和 Key，因此只使用 Web 时可以不在 `.env` 中填写 Key。
- CLI 和 MCP 建议使用 `.env` 或 MCP 客户端的 `env` 配置。
- 旧的 `NEBULA_CANVAS_*` 环境变量仍可读取，但新配置应使用 `JIUGE_CANVA_*`。

## Web 可视化页面

### 启动

```powershell
npm run web
```

打开 [http://127.0.0.1:8787](http://127.0.0.1:8787)。也可以直接从 PowerShell 打开：

```powershell
Start-Process http://127.0.0.1:8787
```

指定监听地址或端口：

```powershell
node bin\jiuge-canva-web.js --host 127.0.0.1 --port 8788
```

安装过 `npm link` 时也可以使用：

```powershell
jiuge-canva-web --port 8788
```

### 首次出图

1. 点击页面右上角的连接状态，填写 API Base URL 和 API Key。
2. 选择模型分组和具体模型。
3. 选择“生成”“本地改图”或“URL 改图”。
4. 填写提示词和该模型支持的输出参数。
5. 点击“生成图像”，在中间结果区查看进度、图片和真实像素。

连接设置的保存范围：

- Base URL 保存在浏览器 `localStorage`。
- API Key 只保存在当前标签页 `sessionStorage`，关闭标签页后清除。
- Key 不会写入 `.env`、任务记录、输出元数据或批次清单。

Web 页面按 PC 浏览器工作台设计，建议浏览器窗口宽度至少 `1180px`。

### 三种模式

- 生成：支持单张和批量任务；批量为多次独立请求，数量 2-12，并发 1-4。
- 本地改图：上传 PNG、JPEG 或 WebP，单次最多 8 张参考图。
- URL 改图：每行填写一个公网 HTTP(S) 图片地址，单次最多 8 个地址。

Image 2 4K 的 Web 批量上限为 10。Web 中的“数量”表示独立请求数，不是单次上游请求的 `n` 参数。

## CLI

CLI 当前提供生图；改图请使用 Web 或 MCP。

查看帮助和模型注册表：

```powershell
npm run cli -- --help
npm run cli -- models
```

### Image 2 1K

```powershell
npm run cli -- image generate `
  --preset image2 `
  --prompt "雨后的未来城市街道，电影感灯光，无文字和水印" `
  --size 1024x1024 `
  --quality high
```

### Image 2 4K

```powershell
npm run cli -- image generate `
  --preset image2_4k `
  --prompt "开阔山谷日出，动漫背景美术，16:9，无文字和水印" `
  --size 3840x2160 `
  --quality high `
  --timeout-ms 1800000
```

单次 Image 2 4K 请求需要多张结果时，可以增加 `--n 1` 到 `--n 10`。

### Nano Banana

```powershell
npm run cli -- image generate `
  --preset nanobanana `
  --prompt "漂浮在云海上的天文岛，无文字和水印" `
  --resolution 2K `
  --aspect-ratio 16:9
```

### Grok Imagine

```powershell
npm run cli -- image generate `
  --preset grok `
  --prompt "写实海岸公路，宽幅 16:9，无人物、文字和水印"
```

Grok 的比例写在提示词中，不要传 `--size`、`--resolution`、`--aspect-ratio`、`--quality` 或 `--n`。

安装过 `npm link` 后，把示例中的 `npm run cli --` 替换成 `jiuge-canva` 即可。

## MCP Server

MCP 使用 stdio，不需要额外开放端口。项目内配置示例位于 `examples/mcp-config.json`。

从源码运行的 MCP 客户端配置：

```json
{
  "mcpServers": {
    "jiuge-canva": {
      "command": "node",
      "args": ["E:/codex/jiuge-canva/bin/jiuge-canva-mcp.js"],
      "env": {
        "APINEBULA_API_KEY": "your_api_key_here",
        "APINEBULA_BASE_URL": "https://img-api.apinebula.ai",
        "JIUGE_CANVA_OUTPUT_DIR": "E:/codex/jiuge-canva/outputs",
        "JIUGE_CANVA_TIMEOUT_MS": "1800000"
      }
    }
  }
}
```

复制到其他目录后，需要把 `args` 和输出目录改成实际绝对路径。安装过 `npm link` 的客户端也可以把命令改为 `jiuge-canva-mcp`。

当前 MCP 工具：

| 工具 | 用途 |
| --- | --- |
| `jiuge_canva_generate_image` | 文本生图 |
| `jiuge_canva_edit_image` | 使用本地参考图改图 |
| `jiuge_canva_edit_image_async` | 使用公网 URL 参考图改图；后缀为兼容保留 |
| `jiuge_canva_get_task` | 查询旧异步图片任务 |

旧的 `nebula_canvas_*` MCP 工具名仍注册为兼容别名。

常用参数包括 `preset`、`model`、`prompt`、`size`、`resolution`、`aspectRatio`、`quality`、`n`、`outputDir` 和 `timeoutMs`。只传所选模型分组支持的参数。

## Codex Skills（可选）

项目将 Skill 按模型分组拆开。`jiuge-canva` 是很薄的默认路由入口；四个专用 Skill 只描述各自协议、模型和参数边界。它们共用同一套 CLI、MCP、REST 和 Web 运行时，不会产生四份后端实现。

安装全部 Skill 到当前 Windows 用户：

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$skillRoot = Join-Path $codexHome "skills"
New-Item -ItemType Directory -Force $skillRoot | Out-Null
Get-ChildItem .\skills -Directory | ForEach-Object {
  Copy-Item -Recurse -Force $_.FullName $skillRoot
}
```

重启 Codex 后可使用：

- `$jiuge-canva`：未指定模型时的默认路由。
- `$nebula-image2-1k`：`gpt-image-2-1k`。
- `$nebula-image2-4k`：固定 `3840x2160` 的 Image2 4K。
- `$nebula-nanobanana`：Nano Banana/Gemini 图片模型。
- `$nebula-grok`：Grok Imagine。

例如：

```text
Use $nebula-image2-4k to generate a wide anime landscape at 3840x2160.
```

如果只需要某一组，也可以只复制对应目录；但要使用未指定模型的默认路由，需要同时安装 `jiuge-canva`。

Skill 只负责选择模型和约束参数，实际执行仍通过 MCP、CLI、REST 或 Web。核心参数注册表位于 `src/models.js`，是唯一事实来源。

### 四个独立 Skill 包

四个模型 Skill 也可以分别打包和安装，不需要安装 `jiuge-canva` 路由 Skill：

```powershell
npm run package:skills
Get-ChildItem .\dist\skills\*.zip
```

产物位于 `dist/skills/`：

```text
nebula-image2-1k.zip
nebula-image2-4k.zip
nebula-nanobanana.zip
nebula-grok.zip
SHA256SUMS.txt
```

只安装一个 Skill：

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$skillRoot = Join-Path $codexHome "skills"
New-Item -ItemType Directory -Force $skillRoot | Out-Null
Expand-Archive .\dist\skills\nebula-image2-4k.zip -DestinationPath $skillRoot -Force
```

独立包内含该模型自己的 `SKILL.md`、UI 元数据、参数配置和 Python 标准库运行器；因此即使没有其他三个 Skill，也可以直接调用该模型。直接运行包内脚本时需要 Python 3.9+，并在进程环境中设置 `APINEBULA_API_KEY`。例如：

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-image2-4k"
python "$skill\scripts\generate_image.py" `
  --prompt "wide anime mountain valley, no text or watermark" `
  --quality high `
  --timeout 1800 `
  --output .\mountain.png
```

独立运行器支持生图、本地参考图编辑、`APINEBULA_BASE_URL`/`--base-url` 覆盖、结果下载和真实像素检查。`dist/` 仅是本地打包产物，已被 Git 忽略，不会进入源码提交。

## 输出文件

默认输出目录为 `outputs/`。

普通任务：

```text
outputs/
├─ <timestamp>-<model>.json
└─ <timestamp>-<model>-1.png
```

Web 批量任务：

```text
outputs/batches/<timestamp>-<batch-id>/
├─ 001.json
├─ 001.png
├─ 002.json
├─ 002.png
└─ manifest.json
```

jiuge-canva 会检查下载图片的签名、MIME、字节数和真实宽高。请求中的尺寸只是上游参数，最终结果请以页面或 `inspections` 中的实际像素为准。

## 参数速查

| 预设 | 输出参数 | 重要限制 |
| --- | --- | --- |
| `image2` | `size=1024x1024`、`quality=auto|low|medium|high` | 单次 `n=1`，不提供 2K/4K |
| `image2_4k` | `size=3840x2160`、质量、`n=1..10` | 固定 4K，建议 30 分钟超时 |
| `nanobanana` | `resolution=1K|2K|4K`、`aspectRatio` | Gemini 2.5 Flash 仅支持 1K |
| `grok` | 比例写入提示词 | 当前 1K，不接受其他输出参数 |

## 项目命令

| 命令 | 作用 |
| --- | --- |
| `npm run web` 或 `npm start` | 启动可视化页面和本地 REST API |
| `npm run cli -- --help` | 查看 CLI 帮助 |
| `npm run cli -- models` | 查看模型能力注册表 |
| `npm run mcp` | 启动 stdio MCP Server |
| `npm run package:skills` | 生成四个独立 Skill ZIP 和 SHA-256 清单 |
| `npm run check` | 运行 Mock 上游与 Web/协议自动检查 |

## 验证安装

```powershell
npm run check
node --check src\apinebula.js
node --check src\models.js
node --check src\cli.js
node --check src\web-server.js
node --check public\app.js
node --check bin\jiuge-canva-mcp.js
node --check bin\jiuge-canva-web.js
npm pack --dry-run
```

`npm run check` 使用本地 Mock API，不会发送真实 APINebula 请求，也不会消耗图片额度。

## 常见问题

### 页面提示“需要 API Key”

点击右上角连接状态，在网页中填写 Key；或者在 `.env` 中设置 `APINEBULA_API_KEY` 后重启服务。

### Base URL 应该怎么填

填写 `https://img-api.apinebula.ai` 这样的根地址，不要填写 `/v1/images/generations`，也不要追加 `/v1`。

### CLI 能否改图

当前不能。请使用 Web 的本地改图、URL 改图，或 MCP 的两个改图工具。

### 为什么请求尺寸和下载图片尺寸不同

上游可能返回与请求元数据不同的真实像素。jiuge-canva 会在保存后读取图片文件并展示实际宽高。

### 任务历史为什么重启后消失

Web 任务列表保存在当前 Node.js 进程内存中；重启后列表会清空，但 `outputs/` 中的图片、JSON 和批次 `manifest.json` 仍然存在。
