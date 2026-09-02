# jiuge-canva

四个彼此独立的 APINebula 图像 Skill 包。每个 Skill 都可以单独安装、
单独调用，不依赖本仓库的其他目录，也不需要 Node.js、数据库或额外的
图像处理库。

## 包含的 Skill

| Skill | APINebula 分组 | 模型 | 适用场景 |
| --- | --- | --- | --- |
| `nebula-image2-1k` | `gpt-image-2-1k` | `gpt-image-2` | Image2 1K 生图和改图 |
| `nebula-image2-4k` | `image2-4k` | `gpt-image-2-4k` | 固定 3840x2160 的 Image2 4K 生图和改图 |
| `nebula-nanobanana` | `nanobanana` | `gemini-3.1-flash-image` | Gemini/Nano Banana，支持分辨率和比例 |
| `nebula-grok` | `Grok` | `grok-imagine-image` | Grok Imagine 生图和改图 |

默认请求根地址是 `https://img-api.apinebula.ai`。Adobe 分组不在本仓库中。

## 目录结构

```text
jiuge-canva/
├─ README.md
├─ LICENSE
├─ scripts/
│  ├─ package_skills.py
│  ├─ package-skills.ps1
│  └─ validate_skills.py
└─ skills/
   ├─ nebula-image2-1k/
   │  ├─ SKILL.md
   │  ├─ agents/openai.yaml
   │  └─ scripts/{config.json,generate_image.py}
   ├─ nebula-image2-4k/
   ├─ nebula-nanobanana/
   └─ nebula-grok/
```

每个目录都包含自己的说明、界面元数据、配置和标准库运行器。配置文件
是该 Skill 参数能力的唯一事实来源，运行器会根据配置动态校验参数。

## 环境要求

- Codex，用于发现和调用 Skill。
- Python 3.9 或更高版本。
- 一个有对应分组权限的 APINebula API Key。
- 不需要安装第三方 Python 包；运行器只使用 Python 标准库。

## 安装

### 从 GitHub 安装全部 Skill

```powershell
git clone https://github.com/jiugeovo/jiuge-canva.git
Set-Location .\jiuge-canva

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$skillRoot = Join-Path $codexHome "skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null

Get-ChildItem -LiteralPath .\skills -Directory | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $skillRoot -Recurse -Force
}
```

重启 Codex 后即可使用 `$nebula-image2-1k`、`$nebula-image2-4k`、
`$nebula-nanobanana` 或 `$nebula-grok`。只复制一个目录也可以，不需要
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

### Image2 1K

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

### Image2 4K

始终请求 `3840x2160`。质量可选 `auto`、`low`、`medium`、`high`，
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

### Grok Imagine

将目标比例直接写入提示词；该 Skill 不接受 Image2 或 Gemini 的输出控制
参数：

```powershell
$skill = ".\skills\nebula-grok"
python "$skill\scripts\generate_image.py" `
  --prompt "cinematic anime coast, wide 16:9 composition, no text" `
  --output .\grok.png
```

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

静态校验四个 Skill，并检查每个运行器的帮助命令：

```powershell
python .\scripts\validate_skills.py
```

运行本地 Mock 请求，验证四种协议、文件保存和像素检查：

```powershell
python .\scripts\validate_skills.py --smoke
```

打包四个独立 ZIP，并生成 SHA-256 清单：

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
nebula-grok.zip
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
