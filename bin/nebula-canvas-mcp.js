#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { APINebulaClient, saveImageResponseArtifacts } from "../src/apinebula.js";
import { getConfig } from "../src/config.js";
import { resolveImageOptions } from "../src/models.js";

const presetSchema = z.enum(["image2", "image2_4k", "nanobanana", "grok"]);
const imageOptionsSchema = {
  model: z.string().optional(),
  preset: presetSchema.optional(),
  n: z.number().int().min(1).max(10).optional(),
  size: z.string().optional(),
  resolution: z.enum(["1K", "2K", "4K"]).optional(),
  aspectRatio: z.string().optional(),
  quality: z.enum(["low", "medium", "high", "auto"]).optional(),
  responseFormat: z.enum(["url", "b64_json"]).optional(),
  inputFidelity: z.enum(["high"]).optional(),
  outputDir: z.string().optional(),
  baseUrl: z.string().url().optional(),
  timeoutMs: z.number().int().positive().optional(),
  noDownload: z.boolean().optional(),
};

const server = new McpServer({
  name: "nebula-canvas",
  version: "0.1.0",
});

server.tool(
  "nebula_canvas_generate_image",
  "Generate images through the documented APINebula Image2, Nano Banana, or Grok protocol and save the result.",
  {
    prompt: z.string().min(1),
    ...imageOptionsSchema,
  },
  async (args) => runImageTool({ args, mode: "generate" }),
);

server.tool(
  "nebula_canvas_edit_image",
  "Edit one or more local images through the selected APINebula image group and save the result.",
  {
    prompt: z.string().min(1),
    imagePaths: z.array(z.string().min(1)).min(1).max(8),
    ...imageOptionsSchema,
  },
  async (args) => runImageTool({
    args,
    mode: "edit-sync",
    images: args.imagePaths.map((imagePath) => ({ path: imagePath })),
  }),
);

server.tool(
  "nebula_canvas_edit_image_async",
  "Edit one or more public image URLs through the selected APINebula image group and save the result.",
  {
    prompt: z.string().min(1),
    imageUrls: z.array(z.string().url()).min(1).max(8),
    ...imageOptionsSchema,
  },
  async (args) => runImageTool({
    args,
    mode: "edit-async",
    images: args.imageUrls.map((url) => ({ url })),
  }),
);

server.tool(
  "nebula_canvas_get_task",
  "Query a legacy APINebula asynchronous image task by id.",
  {
    taskId: z.string().min(1),
    baseUrl: z.string().url().optional(),
  },
  async ({ taskId, baseUrl }) => {
    const client = new APINebulaClient(getConfig({ baseUrl }));
    return textResult(await client.getImageTask(taskId, { detail: true }));
  },
);

async function runImageTool({ args, mode, images = [] }) {
  if (!args.model && !args.preset) throw new Error("Provide either model or preset.");

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
    inputFidelity: args.inputFidelity,
  }, { mode });
  const requestOptions = {
    ...selection.options,
    transport: selection.preset.transport,
    images,
    timeoutMs: config.timeoutMs,
  };

  const client = new APINebulaClient(config);
  const response = mode === "generate"
    ? await client.generateImage(requestOptions)
    : await client.editImage(requestOptions);
  const artifacts = await saveImageResponseArtifacts({
    response,
    model: requestOptions.model,
    outputDir: config.outputDir,
    download: !args.noDownload,
  });

  return textResult({
    status: "completed",
    requestId: response?.id || response?.responseId,
    preset: selection.name,
    group: selection.preset.group,
    transport: selection.preset.transport,
    model: requestOptions.model,
    metadataPath: artifacts.metadataPath,
    imageUrls: artifacts.imageUrls,
    downloadedFiles: artifacts.downloadedFiles,
    inspections: artifacts.inspections,
  });
}

function textResult(value) {
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
  };
}

const transport = new StdioServerTransport();
await server.connect(transport);
