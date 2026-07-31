import path from "node:path";
import { APINebulaClient, saveImageResponseArtifacts } from "./apinebula.js";
import { getConfig } from "./config.js";
import { getPresetSummary, resolveImageOptions } from "./models.js";

export async function runCli(argv = process.argv.slice(2)) {
  const [domain, action, ...rest] = argv;

  if (!domain || domain === "-h" || domain === "--help") {
    printHelp();
    return 0;
  }

  if (domain === "models") {
    console.log(JSON.stringify(getPresetSummary(), null, 2));
    return 0;
  }

  if (domain !== "image" || action !== "generate") {
    throw new Error(`Unknown command: ${[domain, action].filter(Boolean).join(" ")}`);
  }

  const args = parseArgs(rest);
  if (!args.prompt?.trim()) throw new Error("Missing --prompt.");
  if (!args.model && !args.preset) throw new Error("Missing --model or --preset.");

  const config = getConfig({
    baseUrl: args.baseUrl,
    outputDir: args.outputDir,
    timeoutMs: args.timeoutMs,
  });
  const selection = resolveImageOptions(args.preset, {
    model: args.model,
    prompt: args.prompt.trim(),
    n: args.n,
    size: args.size,
    resolution: args.resolution,
    aspectRatio: args.aspectRatio,
    quality: args.quality,
    responseFormat: args.responseFormat,
  });
  const requestOptions = {
    ...selection.options,
    transport: selection.preset.transport,
    timeoutMs: config.timeoutMs,
  };

  console.error(`Generating with ${selection.preset.label} (${requestOptions.model})...`);
  const client = new APINebulaClient(config);
  const response = await client.generateImage(requestOptions);
  const artifacts = await saveImageResponseArtifacts({
    response,
    model: requestOptions.model,
    outputDir: config.outputDir,
    download: !args.noDownload,
  });

  console.log(JSON.stringify({
    status: "completed",
    requestId: response?.id || response?.responseId,
    preset: selection.name,
    group: selection.preset.group,
    transport: selection.preset.transport,
    model: requestOptions.model,
    outputDir: path.resolve(config.outputDir),
    metadataPath: artifacts.metadataPath,
    imageUrls: artifacts.imageUrls,
    downloadedFiles: artifacts.downloadedFiles,
    inspections: artifacts.inspections,
  }, null, 2));

  return 0;
}

function parseArgs(args) {
  const result = {};

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (!arg.startsWith("--")) throw new Error(`Unexpected argument: ${arg}`);

    const [rawKey, inlineValue] = arg.slice(2).split("=", 2);
    const key = toCamel(rawKey);
    if (key === "noDownload") {
      result[key] = true;
      continue;
    }
    if (key === "noWait") {
      throw new Error("--no-wait is no longer supported because documented image groups use synchronous endpoints.");
    }

    const value = inlineValue ?? args[++i];
    if (value === undefined || value.startsWith("--")) throw new Error(`Missing value for --${rawKey}`);
    result[key] = value;
  }

  return result;
}

function toCamel(value) {
  return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function printHelp() {
  console.log(`NebulaCanvas

Usage:
  nebula-canvas image generate --preset <image2|image2_4k|nanobanana|grok> --prompt <prompt> [options]
  nebula-canvas image generate --model <model> --prompt <prompt> [options]
  nebula-canvas models

Options:
  --n <1-10>                       Image2 4K only; other groups return one image
  --size <widthxheight>            Image2 groups only
  --resolution <1K|2K|4K>         Nano Banana only
  --aspect-ratio <ratio>           Nano Banana only; write Grok ratios in the prompt
  --quality <low|medium|high|auto> Image2 groups only
  --response-format <b64_json|url> Image2 groups only
  --output-dir <path>
  --base-url <url>
  --timeout-ms <ms>
  --no-download
`);
}
