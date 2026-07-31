# NebulaCanvas 应用交接文档

> 最后更新：2026-08-01
> 项目目录：`E:\codex\tianwen`
> 远程仓库：`https://github.com/jiugeovo/nebula-canvas.git`
> 文档基线：`https://docs.apinebula.ai/docs/advanced/image`

## 1. 项目定位

NebulaCanvas 是一个本地 APINebula 图片工作台。它把不同图片分组的三套协议统一为 Web、REST、CLI 和 MCP 四种入口，并负责：

- 根据模型分组显示和校验参数。
- 提交文本生图、本地图片编辑和公网 URL 图片编辑。
- 保存远程结果、本地文件和压缩后的元数据。
- 解析图片签名、MIME、字节数与真实宽高。
- 提供淡粉色二次元风格、三栏式的可视化工作台。

Adobe 分组已从产品能力、默认配置、CLI、MCP 和 Web 选择中移除。不要重新引入旧 Adobe/Banana 预设，除非产品需求和新版文档再次明确要求。

## 2. 当前状态

截至本次交接：

- 当前分支为 `main`，开始本轮工作时比 `origin/main` 领先 1 个既有提交。
- 工作区包含本轮未提交改动；提交前必须再次执行 `git status` 和完整验证。
- `tmp/` 是未跟踪临时目录，不要删除、提交或据此判断产品输出。
- `.env` 被 Git 忽略，包含本机配置；不要读取、打印或提交真实 API Key。
- 默认上游根地址已改为 `https://img-api.apinebula.ai`。
- 默认请求超时为 30 分钟，以覆盖 Image2 4K 长请求。
- Web 验证实例使用 `http://127.0.0.1:8788/`，避免干扰原有 8787 服务。

## 3. 模型能力注册表

能力定义集中在 `src/models.js`，所有入口都必须通过 `resolveImageOptions()`，不要在 Web、CLI 或 MCP 单独维护另一份分组逻辑。

| 预设 | 令牌分组 | 默认模型 | Transport | 上游接口 |
| --- | --- | --- | --- | --- |
| `image2` | `gpt-image-2-1k` | `gpt-image-2` | `images` | `/v1/images/generations`、`/v1/images/edits` |
| `image2_4k` | `image2-4k` | `gpt-image-2-4k` | `images` | `/v1/images/generations`、`/v1/images/edits` |
| `nanobanana` | `nanobanana` | `gemini-3.1-flash-image` | `gemini` | `/v1beta/models/{model}:generateContent` |
| `grok` | `Grok` | `grok-imagine-image` | `chat` | `/v1/chat/completions` |

兼容别名：

- `gpt-image-2-1k` -> `image2`
- `image-2-1k` -> `image2`，仅保留旧调用兼容。
- `image2-4k` -> `image2_4k`
- `Grok` -> `grok`

`adobe` 请求必须返回未知预设错误。测试中保留该拒绝断言是有意行为，不代表 Adobe 仍是可用能力。

## 4. 参数规则

### 4.1 Image 2 1K

- 分组：`gpt-image-2-1k`
- 模型：`gpt-image-2`
- 生图尺寸：文档明确验证 `1024x1024`。
- 改图尺寸：`1024x1024`、文档示例值 `1536x1024`。
- `quality`：`auto`、`low`、`medium`、`high`。
- `response_format`：`url`、`b64_json`。
- `n`：只能为 1。
- 编辑时可使用 `input_fidelity=high`。
- 不支持 2K 或 4K。

历史实测说明：即使请求写 `1024x1024`，上游也曾返回约 `1254x1254`。因此 UI 和结果对象展示保存后的真实像素，不把请求参数当成实际尺寸。

### 4.2 Image 2 4K

- 分组：`image2-4k`
- 模型：`gpt-image-2-4k`
- 尺寸固定 `3840x2160`。
- `n` 支持 1–10。
- `quality`：`auto`、`low`、`medium`、`high`。
- `response_format`：`url`、`b64_json`。
- 编辑时可使用 `input_fidelity=high`。
- 建议超时 1800 秒。

文档说明 `response_format=url` 时响应仍可能同时含 `b64_json`。保存逻辑为：

- 默认下载：优先保存内联图片，并写入实际尺寸。
- `noDownload=true` 且存在 URL：不保存内联图片，只保留 URL 与元数据。
- 仅有内联图片：即使 `noDownload=true` 也必须落盘，否则用户得不到可用结果。

### 4.3 Nano Banana

- 分组：`nanobanana`，模型名不带旧前缀。
- 使用 Gemini 原生 `contents` 与 `generationConfig`。
- 图片位于 `candidates[].content.parts[].inlineData`。
- 比例可选：`1:1`、`1:4`、`1:8`、`2:3`、`3:2`、`3:4`、`4:1`、`4:3`、`4:5`、`5:4`、`8:1`、`9:16`、`16:9`、`21:9`。
- 2.5 Flash 与其 preview 仅支持 1K。
- 3.1 Flash、3.1 Flash preview、3 Pro preview 支持 1K/2K/4K。
- 不接受 `size`、`quality`、`responseFormat`、`inputFidelity` 或 `n`。
- 没有远程 URL，因此 UI 隐藏“仅保留远程 URL”。

### 4.4 Grok Imagine

- 分组：`Grok`
- 模型：`grok-imagine-image`
- 生图用字符串消息；改图用同一用户消息中的文字和 `image_url`。
- 结果从 `choices[0].message.content` 的 Markdown 图片链接提取。
- 当前仅支持 1K。
- 比例直接写在提示词里。
- 不接受 `size`、`resolution`、`aspectRatio`、`quality`、`responseFormat`、`inputFidelity` 或 `n`。
- 无输出参数可提交时，Web 会收起整个参数区。

## 5. 架构

```text
Web / REST / CLI / MCP
          |
          v
src/models.js
能力选择、默认值、模型与参数校验
          |
          v
src/apinebula.js
Images / Gemini / Chat 三协议适配
          |
          v
统一结果提取与 artifact 保存
URL + 本地文件 + 元数据 + 实际尺寸
```

### 5.1 关键文件

| 文件 | 职责 |
| --- | --- |
| `src/models.js` | 四分组能力注册表、别名、默认模型、按模式参数校验 |
| `src/apinebula.js` | 三协议客户端、URL/Base64 提取、图片下载、格式与尺寸解析、CDN 回退 |
| `src/config.js` | `.env`、Base URL、输出目录、超时配置 |
| `src/web-server.js` | Web 静态资源、本地 REST、任务状态、批量并发、上传与输出文件服务 |
| `public/index.html` | 三栏工作台和连接设置对话框 |
| `public/app.js` | 模型能力驱动的参数显隐、提交、轮询、结果与真实尺寸渲染 |
| `public/styles.css` | 淡粉色二次元 PC 浏览器布局与组件状态 |
| `src/cli.js` | CLI 生图入口 |
| `bin/nebula-canvas-mcp.js` | MCP 生图、本地改图、URL 改图与旧任务查询 |
| `scripts/check.mjs` | 单元式断言、Mock 上游、REST 与批量集成检查 |

## 6. 上游请求流程

### 6.1 Images API

生图：

```text
POST {baseUrl}/v1/images/generations
Content-Type: application/json
Authorization: Bearer <key>
```

改图：

```text
POST {baseUrl}/v1/images/edits
Content-Type: multipart/form-data
重复 image 字段可提交多张参考图
```

### 6.2 Gemini 原生接口

```text
POST {baseUrl}/v1beta/models/{model}:generateContent
contents[].parts = text + optional inlineData
generationConfig.responseModalities = ["IMAGE"]
generationConfig.imageConfig = aspectRatio + imageSize
```

### 6.3 Grok Chat Completions

```text
POST {baseUrl}/v1/chat/completions
messages[0].content = prompt
或 [text, image_url...]
stream = false
```

旧 `/v1/image-tasks/*` 方法只在 `APINebulaClient` 和 MCP 的 `nebula_canvas_get_task` 中兼容保留，不是 Web、REST、CLI 或 MCP 图片生成/改图的主流程。

## 7. Web 产品设计

### 7.1 视觉方向

- 淡粉色二次元工作台，不使用旧绿色主题。
- 页面背景使用真实风景图 `public/assets/nebula-landscape-image2.webp`。
- 画布区域保持中性，不重复铺背景图。
- PC 浏览器为配置、当前任务、任务记录三栏，建议视口宽度至少 1180px；CSS 保留少量滚动条余量。
- 当前不维护手机端适配，也不提供 Electron、Tauri 等独立桌面客户端。
- 图标使用本地 Lucide 包，不依赖远程 CDN。

### 7.2 交互规则

- 三种模式：生图、本地改图、URL 改图。
- 模型分组切换后，具体模型和输出参数立即按 capability 更新。
- Nano 2.5 模型自动把分辨率限制为 1K。
- Grok 参数区为空时整体隐藏，并提示比例写入 prompt。
- 结果卡显示 `宽x高 · 格式`，数据来自实际文件检查。
- 批量任务按一条父记录展示总进度、完成数和失败项。
- 任务历史仅保存在当前 Node 进程内存，重启后清空；批次 manifest 和图片文件仍在磁盘。

### 7.3 网页连接设置

请求头：

```text
X-Nebula-Base-Url
X-Nebula-Api-Key
```

存储策略：

- Base URL 写入 `localStorage`。
- API Key 只写当前标签页 `sessionStorage`。
- 服务端任务、日志、元数据和 manifest 不回显 API Key。
- “恢复服务端配置”会删除网页覆盖并回到 `.env`。

这套网页输入适合本机 `127.0.0.1` 使用，不应把当前服务未经鉴权直接暴露到公网。

## 8. 本地 REST

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/health` | 当前 Base URL、Key 是否存在、输出目录 |
| `GET` | `/api/presets` | 四分组能力摘要 |
| `GET` | `/api/jobs` | 当前进程任务列表 |
| `POST` | `/api/jobs` | 单次图片生成 |
| `POST` | `/api/batches` | 多次独立生成请求组成的批次 |
| `POST` | `/api/edit-jobs` | multipart 本地改图；JSON URL 改图 |
| `GET` | `/api/jobs/{id}` | 单个本地任务 |
| `GET` | `/api/files/{root}/{path}` | 安全映射的本地输出文件 |

批量限制：

- 全局 `count` 为 2–12。
- Image2 4K 上限为 10。
- 并发为 1–4，且不能超过任务数。
- Web 的“数量”表示独立请求数，不等同于 Image2 4K 单次请求参数 `n`。

## 9. 输出与元数据

默认目录：`outputs/`。

普通任务：

```text
<timestamp>-<model>.json
<timestamp>-<model>-1.png|jpg|webp
```

批量任务：

```text
outputs/batches/<timestamp>-<batch-id>/
├─ 001.json
├─ 001.png
├─ 002.json
├─ 002.png
└─ manifest.json
```

图片检查支持 PNG、JPEG、WebP、GIF。保存失败条件包括：空响应、损坏签名、无法解析尺寸、下载超限或上游没有返回可用 URL/Base64。

元数据中的大字段会替换为 `[omitted]`：

- Images API `b64_json`
- Gemini `inlineData.data`

## 10. 下载与安全边界

- 输入图片最大 32 MB。
- 输出图片下载最大 128 MB。
- 公网 URL 改图拒绝非 HTTP(S)、带用户名密码、localhost、私网、链路本地和保留地址。
- 每次重定向后重新进行公网地址校验。
- 结果下载最多跟随 4 次重定向。
- 下载内容必须通过图片签名和宽高检查。
- 对 `pubimage.apinebula.com` 或 `cdnimage.apinebula.com` 的失败下载，保留完整对象路径并受控尝试 `cdnimage2.apinebula.ai`。
- CDN 根路径 404 不能证明对象不可用；排障时必须测试完整返回路径。

## 11. 配置

`.env.example` 当前变量：

```env
APINEBULA_API_KEY=your_api_key_here
APINEBULA_BASE_URL=https://img-api.apinebula.ai
NEBULA_CANVAS_IMAGE2_MODEL=gpt-image-2
NEBULA_CANVAS_IMAGE2_4K_MODEL=gpt-image-2-4k
NEBULA_CANVAS_NANOBANANA_MODEL=gemini-3.1-flash-image
NEBULA_CANVAS_GROK_MODEL=grok-imagine-image
NEBULA_CANVAS_OUTPUT_DIR=./outputs
NEBULA_CANVAS_TIMEOUT_MS=1800000
NEBULA_CANVAS_WEB_HOST=127.0.0.1
NEBULA_CANVAS_WEB_PORT=8787
```

Base URL 必须是根地址，不能包含 `/v1`、查询串、fragment 或凭据。

## 12. 启动

安装：

```powershell
cd E:\codex\tianwen
npm install
```

启动默认 Web：

```powershell
npm run web
```

启动隔离验证实例：

```powershell
node bin\nebula-canvas-web.js --port 8788
```

CLI：

```powershell
node bin\nebula-canvas.js models
node bin\nebula-canvas.js image generate --preset image2 --prompt "测试图，无文字和水印" --size 1024x1024
```

MCP：

```powershell
npm run mcp
```

## 13. 自动验证

交接前必须运行：

```powershell
npm run check
node --check src\apinebula.js
node --check src\web-server.js
node --check public\app.js
node --check bin\nebula-canvas-mcp.js
git diff --check
```

`scripts/check.mjs` 覆盖：

- Images/Gemini/Chat 请求体构造。
- 四分组与旧别名解析。
- Adobe、Grok 非法参数、Nano 2.5 非法 4K 的拒绝。
- 4K `n`、批量数量和并发约束。
- Base64 清理、URL-only 保存语义、图片签名与尺寸。
- Mock 上游下的 Web REST 单图、批量和文件访问。

这些检查不发送真实 APINebula 请求，不消耗图片额度。

## 14. 已知限制

- CLI 目前只提供生图；改图使用 Web、REST 或 MCP。
- Web 任务历史不持久化，重启服务后只能从输出目录和批次 manifest 恢复文件，不会恢复历史列表。
- MCP 工具名 `nebula_canvas_edit_image_async` 为兼容保留，实际已经按所选分组走同步上游协议。
- MCP 仍保留旧任务查询工具；未来若确认无用户依赖，可单独做破坏性版本移除。
- Image2 1K 的请求尺寸与真实输出尺寸可能不同。
- Nano 与 Grok 的模型列表可能随上游变化；生产调用前可用对应令牌查询 `/v1/models`。
- 本轮自动测试使用 Mock 上游；是否进行真实生图烟测应由拥有额度的维护者明确决定。

## 15. 后续建议

1. 增加持久化任务索引和批次 manifest 恢复入口。
2. 在 Web 高级设置中按 Images 分组开放文档已确认的 `background`、`moderation`、`output_format` 与压缩参数。
3. 为 Image2 4K 单次 `n=1..10` 增加独立 UI 控件，与“批量独立请求数”明确区分。
4. 增加蒙版上传和局部重绘界面；底层 multipart 客户端已保留 mask 能力入口。
5. 为真实 API 烟测建立显式开关，记录返回 URL、本地路径、HTTP 状态和实际像素，不把测试 Key 写入日志。
6. 发布前补充 CI：Node 20/22、Windows/Linux、`npm run check`、`git diff --check`。

## 16. 接手检查清单

- [ ] 阅读本文件与 `README.md`。
- [ ] 执行 `git status --short --branch`，确认未提交改动和分支边界。
- [ ] 不读取、不打印、不提交 `.env`。
- [ ] 不删除或提交 `tmp/`。
- [ ] 核对 `src/models.js` 与在线新版文档。
- [ ] 运行全部自动检查。
- [ ] 在 1280x720 和 1440x900 检查模型切换、参数显隐、弹窗与结果尺寸标签。
- [ ] 提交前扫描旧分组名、旧 Base URL 和旧异步主流程描述。

## 17. 给下一位维护者的简短提示

```text
请接手 E:\codex\tianwen 的 NebulaCanvas。先阅读 NEBULA_CANVAS_HANDOFF.md 和 README.md，再检查 git status。当前产品只启用 image2、image2_4k、nanobanana、grok 四个预设，分别走 Images API、Gemini generateContent 和 Chat Completions；Adobe 已移除。能力与参数以 src/models.js 和 https://docs.apinebula.ai/docs/advanced/image 为准。默认根地址是 https://img-api.apinebula.ai，Web 支持标签页临时 Key。产品只维护 PC 浏览器可视化页面、CLI 和 MCP，不维护手机端或独立桌面客户端。不要读取或提交 .env，不要删除或提交 tmp/。完成后运行 npm run check、相关 node --check 和 git diff --check，并在 1280x720 与 1440x900 验证 UI。
```
