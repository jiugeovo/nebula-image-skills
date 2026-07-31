import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  APINebulaClient,
  buildChatPayload,
  buildEditFields,
  buildGeminiPayload,
  buildGenerationPayload,
  extractImageUrls,
  inspectImageBuffer,
  saveImageResponseArtifacts,
  stringifyJsonForRequest,
} from "../src/apinebula.js";
import { applyPreset, getPresetSummary, resolveImageOptions } from "../src/models.js";
import {
  compactJobForMemory,
  fileUrl,
  runWithConcurrency,
  startWebServer,
  summarizeBatch,
} from "../src/web-server.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

const generationPayload = buildGenerationPayload({
  model: "gpt-image-2",
  prompt: "test",
  size: "1024x1024",
  quality: "high",
  responseFormat: "url",
});
assert(generationPayload.model === "gpt-image-2", "Images payload model");
assert(generationPayload.size === "1024x1024", "Images payload size");
assert(!("resolution" in generationPayload), "Images payload omits resolution");
assert(!("aspect_ratio" in generationPayload), "Images payload omits aspect ratio");

const geminiPayload = buildGeminiPayload({
  prompt: "test",
  resolution: "4K",
  aspectRatio: "16:9",
});
assert(geminiPayload.generationConfig.imageConfig.imageSize === "4K", "Gemini image size");
assert(geminiPayload.generationConfig.imageConfig.aspectRatio === "16:9", "Gemini aspect ratio");
assert(geminiPayload.generationConfig.responseModalities[0] === "IMAGE", "Gemini image modality");

const chatPayload = buildChatPayload({ model: "grok-imagine-image", prompt: "test" });
assert(chatPayload.messages[0].content === "test", "Grok prompt payload");
assert(chatPayload.stream === false, "Grok disables streaming");

const grokEditPayload = buildChatPayload(
  { model: "grok-imagine-image", prompt: "edit" },
  ["data:image/png;base64,AA=="],
);
assert(Array.isArray(grokEditPayload.messages[0].content), "Grok edit uses multimodal content");
assert(grokEditPayload.messages[0].content[1].image_url.url.startsWith("data:image/png"), "Grok edit image URL payload");

const geminiEditPayload = buildGeminiPayload(
  { prompt: "edit", resolution: "1K", aspectRatio: "1:1" },
  [{ mimeType: "image/png", data: "AA==" }],
);
assert(geminiEditPayload.contents[0].parts[1].inlineData.mimeType === "image/png", "Gemini edit inline image payload");

const editFields = buildEditFields({
  model: "gpt-image-2",
  prompt: "edit",
  size: "1536x1024",
  quality: "high",
  responseFormat: "url",
  inputFidelity: "high",
});
assert(editFields.input_fidelity === "high", "edit input fidelity");
assert(editFields.response_format === "url", "edit response format");

const asciiJson = stringifyJsonForRequest({ prompt: "古风人物", model: "gpt-image-2" });
assert(asciiJson.includes("\\u53e4\\u98ce\\u4eba\\u7269"), "request JSON escapes non-ASCII");
assert(!asciiJson.includes("古风人物"), "request JSON is ASCII-safe");

const urls = extractImageUrls({
  detail: { data: [{ download_url: "https://example.com/a.png" }] },
  choices: [{ message: { content: "![image](https://example.com/b.jpg)" } }],
});
assert(urls.join(",") === "https://example.com/a.png,https://example.com/b.jpg", "extract image URLs across protocols");

const inspection = inspectImageBuffer(png);
assert(inspection.mimeType === "image/png", "PNG signature inspection");
assert(inspection.width === 1 && inspection.height === 1, "PNG dimension inspection");

const presetSummary = getPresetSummary();
assert(presetSummary.length === 4, "four non-Adobe presets");
assert(!presetSummary.some((preset) => /adobe/i.test(`${preset.name} ${preset.group}`)), "Adobe preset removed");
assert(presetSummary.find((preset) => preset.name === "image2")?.group === "gpt-image-2-1k", "official 1K group name");
assert(presetSummary.find((preset) => preset.name === "image2_4k")?.transport === "images", "4K Images transport");
assert(presetSummary.find((preset) => preset.name === "nanobanana")?.transport === "gemini", "Nano Gemini transport");
assert(presetSummary.find((preset) => preset.name === "grok")?.transport === "chat", "Grok chat transport");
assert(resolveImageOptions("gpt-image-2-1k", { prompt: "x" }).name === "image2", "official group alias");
assert(resolveImageOptions("image-2-1k", { prompt: "x" }).name === "image2", "legacy 1K alias");
assertThrows(
  () => resolveImageOptions("image2", { prompt: "x", size: "1536x1024" }),
  /size=1536x1024 is not supported/,
  "1K generation size follows the documented value",
);
assert(
  resolveImageOptions("image2", { prompt: "x", size: "1536x1024" }, { mode: "edit-sync" }).options.size === "1536x1024",
  "1K edit accepts the documented landscape size",
);
assert(resolveImageOptions("image2_4k", { prompt: "x", n: "10" }).options.n === 10, "4K n normalization");
assertThrows(() => resolveImageOptions("adobe", { prompt: "x" }), /Unknown image preset/, "removed Adobe preset rejected");
assertThrows(() => resolveImageOptions("grok", { prompt: "x", size: "1024x1024" }), /not supported/, "Grok size rejected");
assertThrows(() => resolveImageOptions("grok", { prompt: "x", n: 1 }), /n is not supported/, "Grok n rejected");
assertThrows(
  () => resolveImageOptions("nanobanana", { prompt: "x", responseFormat: "url" }),
  /responseFormat is not supported/,
  "Nano response format rejected",
);
assertThrows(
  () => resolveImageOptions("nanobanana", { model: "gemini-2.5-flash-image", prompt: "x", resolution: "4K", aspectRatio: "1:1" }),
  /only supports 1K/,
  "Nano 2.5 4K rejected",
);

process.env.NEBULA_CANVAS_NANOBANANA_MODEL = "gemini-3.1-flash-image-preview";
assert(applyPreset("nanobanana", { prompt: "x" }).model === "gemini-3.1-flash-image-preview", "environment model override");
delete process.env.NEBULA_CANVAS_NANOBANANA_MODEL;

const compactedJob = compactJobForMemory({
  configOverrides: { apiKey: "secret" },
  remoteTask: {
    data: [{ b64_json: "x".repeat(100) }],
    candidates: [{ content: { parts: [{ inlineData: { mimeType: "image/png", data: "y".repeat(100) } }] } }],
  },
});
assert(!compactedJob.configOverrides?.apiKey, "compact removes API key");
assert(compactedJob.remoteTask.data[0].b64_json === "[omitted]", "compact removes Images Base64");
assert(compactedJob.remoteTask.candidates[0].content.parts[0].inlineData.data === "[omitted]", "compact removes Gemini Base64");

const batchSummary = summarizeBatch([
  { status: "completed" },
  { status: "failed" },
  { status: "running" },
  { status: "queued" },
]);
assert(batchSummary.completed === 1 && batchSummary.failed === 1, "batch terminal summary");
assert(batchSummary.active === 1 && batchSummary.queued === 1, "batch active summary");
assert(batchSummary.finished === 2, "batch finished summary");

let activeWorkers = 0;
let maxActiveWorkers = 0;
const processedItems = [];
await runWithConcurrency([0, 1, 2, 3, 4], 2, async (item) => {
  activeWorkers += 1;
  maxActiveWorkers = Math.max(maxActiveWorkers, activeWorkers);
  await delay(5);
  processedItems.push(item);
  activeWorkers -= 1;
});
assert(maxActiveWorkers === 2, "batch concurrency helper");
assert(processedItems.sort().join(",") === "0,1,2,3,4", "batch processes every item");

const skillFile = path.join(root, "skills", "nebula-canvas", "SKILL.md");
const skillContent = fs.readFileSync(skillFile, "utf8");
assert(skillContent.startsWith("---\n"), "skill frontmatter");
assert(skillContent.includes("name: nebula-canvas"), "skill name");

const tempOutputDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), "nebula-canvas-check-"));
const nestedOutputDir = path.join(tempOutputDir, "nested");
const tempImage = path.join(nestedOutputDir, "check.png");
await fs.promises.mkdir(nestedOutputDir);
await fs.promises.writeFile(tempImage, png);

const customFileUrl = fileUrl(tempImage, tempOutputDir);
assert(/^\/api\/files\/[0-9a-f-]+\/nested\/check\.png$/.test(customFileUrl), "custom output file URL");

const mockApi = await startMockApi();
const previousEnv = {
  apiKey: process.env.APINEBULA_API_KEY,
  baseUrl: process.env.APINEBULA_BASE_URL,
  timeout: process.env.NEBULA_CANVAS_TIMEOUT_MS,
};
process.env.APINEBULA_API_KEY = "test-key";
process.env.APINEBULA_BASE_URL = mockApi.baseUrl;
process.env.NEBULA_CANVAS_TIMEOUT_MS = "5000";

const directClient = new APINebulaClient({
  apiKey: "test-key",
  baseUrl: mockApi.baseUrl,
  outputDir: tempOutputDir,
  pollIntervalMs: 5,
  timeoutMs: 5000,
});

const geminiResponse = await directClient.generateImage({
  transport: "gemini",
  model: "gemini-3.1-flash-image",
  prompt: "mock Gemini",
  resolution: "1K",
  aspectRatio: "1:1",
});
const geminiArtifacts = await saveImageResponseArtifacts({
  response: geminiResponse,
  model: "gemini-3.1-flash-image",
  outputDir: tempOutputDir,
  download: false,
  fileStem: "gemini-check",
});
assert(geminiArtifacts.downloadedFiles.length === 1, "inline-only Gemini image is saved");
assert(inspectImageBuffer(await fs.promises.readFile(geminiArtifacts.downloadedFiles[0])).width === 1, "saved Gemini image is valid");
const geminiMetadata = JSON.parse(await fs.promises.readFile(geminiArtifacts.metadataPath, "utf8"));
assert(geminiMetadata.candidates[0].content.parts[0].inlineData.data === "[omitted]", "Gemini metadata omits Base64");

const urlOnlyArtifacts = await saveImageResponseArtifacts({
  response: {
    data: [{ url: `${mockApi.baseUrl}/images/generated-1.png`, b64_json: png.toString("base64") }],
  },
  model: "gpt-image-2-4k",
  outputDir: tempOutputDir,
  download: false,
  fileStem: "url-only-check",
});
assert(urlOnlyArtifacts.imageUrls.length === 1, "URL is retained when no-download is enabled");
assert(urlOnlyArtifacts.downloadedFiles.length === 0, "no-download skips inline data when a URL exists");

const grokResponse = await directClient.generateImage({
  transport: "chat",
  model: "grok-imagine-image",
  prompt: "mock Grok",
});
assert(extractImageUrls(grokResponse)[0].endsWith("/images/grok.png"), "Grok Markdown URL response");

const server = await startWebServer({ host: "127.0.0.1", port: 0 });
try {
  assert(server.port > 0, "dynamic Web port");
  const baseUrl = `http://${server.host}:${server.port}`;

  const healthResponse = await fetch(`${baseUrl}/api/health`);
  assert(healthResponse.ok, "Web health endpoint");

  const customHealthResponse = await fetch(`${baseUrl}/api/health`, {
    headers: {
      "X-Nebula-Base-Url": mockApi.baseUrl,
      "X-Nebula-Api-Key": "web-test-key",
    },
  });
  const customHealth = await customHealthResponse.json();
  assert(customHealth.baseUrl === mockApi.baseUrl, "Web base URL override");
  assert(customHealth.apiKeyConfigured && customHealth.usingCustomApiKey, "Web API key override");

  const presetsResponse = await fetch(`${baseUrl}/api/presets`);
  const presets = (await presetsResponse.json()).presets;
  assert(presets.length === 4 && !presets.some((preset) => preset.name === "adobe"), "Web exposes non-Adobe presets");

  const invalidBaseUrlResponse = await fetch(`${baseUrl}/api/health`, {
    headers: { "X-Nebula-Base-Url": "file:///tmp/invalid" },
  });
  assert(invalidBaseUrlResponse.status === 400, "invalid Web base URL");

  const iconResponse = await fetch(`${baseUrl}/vendor/lucide.js`);
  assert(iconResponse.ok && iconResponse.headers.get("content-type")?.startsWith("text/javascript"), "local icon bundle");

  const customFileResponse = await fetch(`${baseUrl}${customFileUrl}`);
  assert(customFileResponse.ok && (await customFileResponse.arrayBuffer()).byteLength === png.length, "custom output file route");

  const invalidJsonResponse = await fetch(`${baseUrl}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{",
  });
  assert(invalidJsonResponse.status === 400, "invalid JSON status");
  assert((await invalidJsonResponse.json()).error.code === "invalid_json", "invalid JSON code");

  await assertPostStatus(baseUrl, "/api/jobs", { preset: "adobe", prompt: "test" }, 400, "removed Adobe request");
  await assertPostStatus(baseUrl, "/api/jobs", { preset: "grok", prompt: "test", size: "1024x1024" }, 400, "Grok invalid size");
  await assertPostStatus(baseUrl, "/api/jobs", { preset: "grok", prompt: "test", responseFormat: "url" }, 400, "Grok invalid response format");
  await assertPostStatus(baseUrl, "/api/edit-jobs", {
    preset: "grok",
    prompt: "test",
    imageUrls: ["not-a-url"],
  }, 400, "URL edit rejects invalid image URL");
  await assertPostStatus(baseUrl, "/api/jobs", {
    preset: "nanobanana",
    model: "gemini-2.5-flash-image",
    prompt: "test",
    resolution: "4K",
    aspectRatio: "1:1",
  }, 400, "Nano 2.5 invalid 4K");
  await assertPostStatus(baseUrl, "/api/jobs", { preset: "image2", prompt: "   " }, 400, "blank prompt");
  await assertPostStatus(baseUrl, "/api/batches", { preset: "image2_4k", prompt: "test", count: 11, concurrency: 2 }, 400, "4K batch limit");
  await assertPostStatus(baseUrl, "/api/batches", { preset: "image2", prompt: "test", count: 2, concurrency: 4 }, 400, "batch concurrency limit");

  const batchOutputDir = path.join(tempOutputDir, "batch-output");
  const batchResponse = await fetch(`${baseUrl}/api/batches`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Nebula-Base-Url": mockApi.baseUrl,
      "X-Nebula-Api-Key": "web-test-key",
    },
    body: JSON.stringify({
      preset: "image2",
      prompt: "batch integration test",
      count: 3,
      concurrency: 2,
      outputDir: batchOutputDir,
    }),
  });
  assert(batchResponse.status === 202, "batch accepted");
  const acceptedBatch = await batchResponse.json();
  assert(!JSON.stringify(acceptedBatch).includes("web-test-key"), "batch response omits Web API key");
  assert(!acceptedBatch.configOverrides && !acceptedBatch.request?.baseUrl, "batch response omits connection config");

  const completedBatch = await waitForJob(baseUrl, acceptedBatch.id);
  assert(completedBatch.status === "completed", "batch completed");
  assert(completedBatch.batch.summary.completed === 3 && completedBatch.batch.summary.failed === 0, "batch item summary");
  assert(mockApi.maxActive === 2, "batch integration concurrency");
  assert(completedBatch.artifacts.downloadedFiles.length === 3, "batch downloaded files");
  assert(completedBatch.artifacts.downloadedFiles.every((file) => /^00[1-3]\.png$/.test(path.basename(file.path))), "batch numbered files");
  assert(completedBatch.artifacts.downloadedFiles.every((file) => file.width === 1 && file.height === 1), "batch exposes actual dimensions");

  const manifest = JSON.parse(await fs.promises.readFile(completedBatch.batch.manifestPath, "utf8"));
  assert(manifest.batch.items.length === 3, "batch manifest items");
  assert(!JSON.stringify(manifest).includes("test-key"), "batch manifest omits environment API key");
  assert(!JSON.stringify(manifest).includes("web-test-key"), "batch manifest omits Web API key");
  assert(!manifest.configOverrides && !manifest.request?.baseUrl, "batch manifest omits connection config");

  const missingRouteResponse = await fetch(`${baseUrl}/api/missing`);
  assert(missingRouteResponse.status === 404, "missing API route");
} finally {
  await server.close();
  await mockApi.close();
  restoreEnv("APINEBULA_API_KEY", previousEnv.apiKey);
  restoreEnv("APINEBULA_BASE_URL", previousEnv.baseUrl);
  restoreEnv("NEBULA_CANVAS_TIMEOUT_MS", previousEnv.timeout);
  await fs.promises.rm(tempOutputDir, { recursive: true, force: true });
}

console.log("NebulaCanvas checks passed.");

function assert(condition, message) {
  if (!condition) throw new Error(`Check failed: ${message}`);
}

function assertThrows(callback, pattern, message) {
  try {
    callback();
  } catch (error) {
    assert(pattern.test(error?.message || String(error)), message);
    return;
  }
  throw new Error(`Check failed: ${message}`);
}

async function assertPostStatus(baseUrl, pathname, body, status, message) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  assert(response.status === status, message);
}

async function startMockApi() {
  let nextImage = 0;
  let active = 0;
  let maxActive = 0;
  let baseUrl;
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, baseUrl);

    if (request.method === "POST" && url.pathname === "/v1/images/generations") {
      await consumeRequest(request);
      active += 1;
      maxActive = Math.max(maxActive, active);
      await delay(30);
      const imageId = ++nextImage;
      active -= 1;
      respondJson(response, 200, {
        created: Date.now(),
        data: [{ url: `${baseUrl}/images/generated-${imageId}.png` }],
      });
      return;
    }

    if (request.method === "POST" && /^\/v1beta\/models\/[^/]+:generateContent$/.test(url.pathname)) {
      await consumeRequest(request);
      respondJson(response, 200, {
        candidates: [{ content: { role: "model", parts: [{ inlineData: { mimeType: "image/png", data: png.toString("base64") } }] }, finishReason: "STOP" }],
        modelVersion: "gemini-3.1-flash-image",
        responseId: "mock-gemini",
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/v1/chat/completions") {
      await consumeRequest(request);
      respondJson(response, 200, {
        id: "mock-grok",
        model: "grok-imagine-image",
        choices: [{ message: { role: "assistant", content: `![image](${baseUrl}/images/grok.png)` }, finish_reason: "stop" }],
      });
      return;
    }

    if (request.method === "GET" && /^\/images\/(generated-\d+|grok)\.png$/.test(url.pathname)) {
      response.writeHead(200, { "Content-Type": "image/png", "Content-Length": png.length });
      response.end(png);
      return;
    }

    respondJson(response, 404, { error: { message: "Mock route not found." } });
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  baseUrl = `http://127.0.0.1:${address.port}`;

  return {
    baseUrl,
    get maxActive() {
      return maxActive;
    },
    close: () => new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve()))),
  };
}

async function consumeRequest(request) {
  for await (const _chunk of request) {
    // Consume request data before responding.
  }
}

async function waitForJob(baseUrl, jobId) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const response = await fetch(`${baseUrl}/api/jobs/${jobId}`, { signal: AbortSignal.timeout(1000) });
    const job = await response.json();
    if (["completed", "partial", "failed"].includes(job.status)) return job;
    await delay(10);
  }
  throw new Error(`Timed out waiting for local batch ${jobId}.`);
}

function respondJson(response, statusCode, value) {
  const body = Buffer.from(JSON.stringify(value));
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Content-Length": body.length,
  });
  response.end(body);
}

function restoreEnv(name, value) {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
