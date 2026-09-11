# nebula-image-skills

三个彼此独立的 APINebula 图像 Skill 包。每个 Skill 都可以单独安装、
单独调用，不依赖本仓库的其他目录，也不需要 Node.js、数据库或额外的
图像处理库。

## 包含的 Skill

| Skill | APINebula 分组 | 默认模型 | 适用场景 |
| --- | --- | --- | --- |
| `nebula-image2-1k` | `gpt-image-2-1k` | `gpt-image-2.5` | 1K 概念稿、插画、构图尝试和参考图局部修改 |
| `nebula-image2-4k` | `image2-4k` | `gpt-image-2-4k` | 16:9 风景、桌面壁纸、大尺寸插画和参考图改图 |
| `nebula-nanobanana` | `nanobanana` | `gemini-3.1-flash-image` | Gemini/Nano Banana 插画、参考图改图及不同比例、分辨率的图片版本 |

默认请求根地址是 `https://img-api.apinebula.ai`。Adobe 分组不在本仓库中。

## 目录结构

```text
nebula-image-skills/
├─ README.md
├─ LICENSE
├─ scripts/
│  ├─ package_skills.py
│  ├─ package-skills.ps1
│  └─ validate_skills.py
├─ tests/
│  └─ test_model_selection.py
└─ skills/
   ├─ nebula-image2-1k/
   │  ├─ SKILL.md
   │  ├─ agents/openai.yaml
   │  └─ scripts/{config.json,generate_image.py}
   ├─ nebula-image2-4k/
   └─ nebula-nanobanana/
```

每个目录都包含自己的说明、界面元数据、配置和标准库运行器。配置文件
定义默认值和本地参数校验规则，实际可调用的模型及参数由服务端和 Key 权限决定。

## 环境要求

- Codex，用于发现和调用 Skill。
- Python 3.9 或更高版本。
- 一个有对应分组权限的 APINebula API Key。
- 不需要安装第三方 Python 包；运行器只使用 Python 标准库。

## 安装

### 从 GitHub 安装全部 Skill

```powershell
git clone https://github.com/jiugeovo/nebula-image-skills.git
Set-Location .\nebula-image-skills

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$skillRoot = Join-Path $codexHome "skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null

Get-ChildItem -LiteralPath .\skills -Directory | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $skillRoot -Recurse -Force
}
```

重启 Codex 后即可使用 `$nebula-image2-1k`、`$nebula-image2-4k` 或
`$nebula-nanobanana`。只复制一个目录也可以，不需要
安装其他 Skill。

### 从独立 ZIP 安装

先生成 ZIP：

```powershell
python .\scripts\package_skills.py
```

然后把需要的包解压到 Skill 根目录：

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$skillRoot = Join-Path $codexHome "skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Expand-Archive -LiteralPath .\dist\skills\nebula-image2-4k.zip -DestinationPath $skillRoot -Force
```

ZIP 内已经包含完整的 Skill 目录名，解压后可以直接被 Codex 发现。

## 配置

建议只在当前 PowerShell 进程中设置 Key：

```powershell
$env:APINEBULA_API_KEY = "<your-api-key>"
$env:APINEBULA_BASE_URL = "https://img-api.apinebula.ai"
$env:APINEBULA_OUTPUT_DIR = (Join-Path (Get-Location) "outputs")
```

也可以只对一次请求设置：

```powershell
$env:APINEBULA_API_KEY = "<your-api-key>"
python .\skills\nebula-image2-1k\scripts\generate_image.py `
  --prompt "anime landscape, no text or watermark" `
  --output .\image.png
```

配置规则：

- `APINEBULA_API_KEY` 是唯一必需的认证变量。
- `APINEBULA_BASE_URL` 和 `--base-url` 接受 HTTP(S) 根地址；末尾的 `/v1`
  会自动规范化。
- `APINEBULA_OUTPUT_DIR` 只在没有传 `--output` 时生效。
- 不要把真实 Key 写入提示词、Skill 文件、README、输出 JSON 或 Git 提交。
- `--base-url` 优先级高于 `APINEBULA_BASE_URL`。

### 自定义模型

模型按以下顺序选择，使用第一个非空值：

```text
--model > 当前 Skill 的模型环境变量 > scripts/config.json 中的 model
```

| Skill | 模型环境变量 | 默认值 |
| --- | --- | --- |
| `nebula-image2-1k` | `APINEBULA_IMAGE2_1K_MODEL` | `gpt-image-2.5` |
| `nebula-image2-4k` | `APINEBULA_IMAGE2_4K_MODEL` | `gpt-image-2-4k` |
| `nebula-nanobanana` | `APINEBULA_NANOBANANA_MODEL` | `gemini-3.1-flash-image` |

不传 `--model` 且环境变量未设置、为空或只有空格时，继续使用默认模型。
Image2 的 `--model` 为空或只有空格时也会跳过；模型名两端的空白会被去除。
不同 Skill 使用独立变量，切换 4K 模型不会改动 1K 默认值。

4K 分组的已知模型包括 `gpt-image-2-4k`、`gpt-image-2.5-flare` 和
`gpt-image-2.5-sunburst`。配置中的
`available_models` 只用于记录已知名称，不是限制列表；Image2 可直接传入新的兼容模型名。

临时为本次请求选择 Flare，并查看最终参数（不调用生图接口、不消耗额度）：

```powershell
$skill = ".\skills\nebula-image2-4k"
python "$skill\scripts\generate_image.py" `
  --model "gpt-image-2.5-flare" `
  --prompt "wide anime mountain valley at sunrise, no text or watermark" `
  --dry-run
```

去掉 `--dry-run`，加上 `--output .\flare.png` 即可请求并保存图片。
将模型名换成 `gpt-image-2.5-sunburst` 可以选用 Sunburst。
如果同一 PowerShell 会话内要连续使用一个模型，可以设置环境变量：

```powershell
$env:APINEBULA_IMAGE2_4K_MODEL = "gpt-image-2.5-sunburst"
# 后续不传 --model 的 4K 请求都会选用 Sunburst。
python "$skill\scripts\generate_image.py" --prompt "anime landscape" --dry-run
```

恢复默认模型时清除环境变量，并省略 `--model`：

```powershell
# 清除覆盖，恢复 config.json 默认值：
Remove-Item Env:APINEBULA_IMAGE2_4K_MODEL -ErrorAction SilentlyContinue
```

也可以直接在 Codex 中指定：

```text
用 $nebula-image2-4k，模型选 gpt-image-2.5-flare，生成一张动漫山谷风景。
```

自定义模型需要支持当前 Skill 的协议和尺寸、质量、参考图等参数。设置模型名
不会改变 Key 的分组权限，也不会放宽本地尺寸限制。Nano Banana 仍校验配置中
登记的模型与分辨率组合。`--dry-run` 只检查本地参数和模型选择，无法证明服务端
可用性、生成质量或实际返回尺寸；服务端拒绝请求时不会自动换回默认模型重试。

## 使用方式

所有 Skill 使用同一个调用形式：

```powershell
python <skill>\scripts\generate_image.py `
  --prompt "<prompt>" `
  [Skill 专属参数] `
  [--reference <本地图片或公网图片 URL>] `
  [--output <图片路径>]
```

重复 `--reference` 可以传入多张参考图；只要存在参考图，就会自动走改图
请求。长提示词可以放进 UTF-8 文件：

```powershell
python <skill>\scripts\generate_image.py `
  --prompt-file .\prompt.txt `
  --output .\result.png
```

### Image2 1K（默认 `gpt-image-2.5`）

`nebula-image2-1k` 使用 APINebula 的 `gpt-image-2-1k` 分组，请求模型默认是
`gpt-image-2.5`，可以通过 `--model` 或专属环境变量覆盖。适合构图、风格尝试和局部修改。
生成默认是 `1024x1024`，质量可选 `auto`、`low`、`medium`、`high`。改图
可以用 `--size WIDTHxHEIGHT`，配置允许的尺寸以及自定义上限为单边
256 到 2048 像素、总像素不超过 4MP：

```powershell
$skill = ".\skills\nebula-image2-1k"
python "$skill\scripts\generate_image.py" `
  --prompt "anime city after rain, clean composition, no text" `
  --quality high `
  --output .\image2-1k.png
```

### Image2 4K（默认 `gpt-image-2-4k`）

适合横向风景、桌面壁纸和大尺寸插画。始终请求 `3840x2160`，切换模型也沿用这个尺寸。
默认使用 `gpt-image-2-4k`；Flare 和 Sunburst 的选择见上方“自定义模型”。
质量可选 `auto`、`low`、`medium`、`high`，
`--n` 可设置 1 到 10 张独立结果：

```powershell
$skill = ".\skills\nebula-image2-4k"
python "$skill\scripts\generate_image.py" `
  --prompt "wide anime mountain valley at sunrise, 16:9, no text" `
  --quality high `
  --n 2 `
  --timeout 1800 `
  --output .\image2-4k.png
```

### Nano Banana

使用 `--resolution` 和 `--aspect-ratio`：

```powershell
$skill = ".\skills\nebula-nanobanana"
python "$skill\scripts\generate_image.py" `
  --prompt "soft pink anime garden, no text or watermark" `
  --resolution 2K `
  --aspect-ratio 16:9 `
  --output .\nanobanana.png
```

可用模型、模型对应的分辨率和比例以该目录的 `scripts/config.json` 为准。
可以用 `--model` 或 `APINEBULA_NANOBANANA_MODEL` 选择其他已配置模型。

## 模型选择的实现方法

这里使用的是“配置覆盖”和“默认值回退”：`argparse` 解析命令行中的 `--model`，
`os.environ.get` 读取当前 Skill 配置的环境变量，`config.json` 保存默认值。
核心逻辑在每个 Skill 的 `scripts/generate_image.py` 的 `resolve_settings` 中：

```python
model_env = str(config.get("model_env", "")).strip()
env_model = os.environ.get(model_env, "").strip() if model_env else ""
selected_model = (args.model or "").strip() or env_model or str(config["model"]).strip()
```

Python 的 `or` 会返回从左到右第一个非空值，`.strip()` 去掉字符串两端的空白。
因此本次参数有值就优先用本次参数，否则依次读取环境变量和配置默认值。
改变长期默认值只需编辑对应 `config.json` 的 `model`，无需修改 Python。

解析后的模型统一放入 `settings["model"]`，生图 JSON、改图 multipart 表单以及
Gemini 请求路径都从这里取值，dry-run 和结果 JSON 也记录同一个请求模型。
这避免了发送模型与本地记录不一致，但不能证明上游内部实际路由到了哪个模型。
三个 Skill 各自包含相同的运行器，所以每个包仍能独立安装运行。

## 结果与文件

成功后，运行器会：

1. 下载或解码上游返回的图片。
2. 检查 PNG、JPEG、WebP 或 GIF 文件签名和真实宽高。
3. 使用原子写入保存图片，避免留下半截文件。
4. 生成同名的脱敏 JSON sidecar，记录请求摘要、响应信息和 SHA-256。

`--output result.png` 会生成 `result.png` 和 `result.json`。不传
`--output` 时会在输出目录生成带 UTC 时间戳的文件名。最终分辨率以保存
后的实际像素为准，不以请求参数或响应中的文字为准。

## 校验与打包

静态校验三个 Skill，并检查每个运行器的帮助命令：

```powershell
python .\scripts\validate_skills.py
```

运行模型选择回归测试，再通过本地 Mock 验证 Images/Gemini 协议、文件保存和像素检查：

```powershell
python -m unittest discover -s tests -v
python .\scripts\validate_skills.py --smoke
```

打包三个独立 ZIP，并生成 SHA-256 清单：

```powershell
python .\scripts\package_skills.py
# Windows PowerShell 也可以：
& .\scripts\package-skills.ps1
```

产物位于 `dist/skills/`，包括：

```text
nebula-image2-1k.zip
nebula-image2-4k.zip
nebula-nanobanana.zip
SHA256SUMS.txt
```

打包脚本只包含 Skill 需要的文件，并排除 Python 缓存、临时文件和本地
输出。ZIP 可以脱离 GitHub 仓库单独分发。

## 常见问题

### 提示没有 API Key

确认当前 PowerShell 进程存在 `$env:APINEBULA_API_KEY`，并在同一个进程
中运行 Python。不要把 Key 放到命令行参数中。

### Base URL 怎么填写

填写类似 `https://img-api.apinebula.ai` 的根地址。填写了 `/v1` 也会被
自动处理，但不要填写具体的接口路径。

### 请求成功但尺寸不一致

部分上游响应会返回与请求元数据不同的图片。运行器会读取实际文件头，
请以终端 JSON 和 sidecar 中的 `width`、`height` 为准。

### 大图超时

Image2 4K 适当增加 `--timeout`，例如 `1800` 秒；这只影响当前请求，
不会修改系统设置。

## License

本项目按 [LICENSE](LICENSE) 发布。
