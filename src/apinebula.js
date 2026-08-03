import crypto from "node:crypto";
import dns from "node:dns/promises";
import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import net from "node:net";
import path from "node:path";
import MultipartFormData from "form-data";
import { ensureApiKey, ensureOutputDir } from "./config.js";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);
const MAX_INPUT_IMAGE_BYTES = 32 * 1024 * 1024;
const MAX_OUTPUT_IMAGE_BYTES = 128 * 1024 * 1024;
const FALLBACK_CDN_HOSTS = new Set(["pubimage.apinebula.com", "cdnimage.apinebula.com"]);

export class APINebulaClient {
  constructor(config) {
    this.config = config;
    ensureApiKey(config);
  }

  async generateImage(options) {
    if (options.transport === "gemini") {
      return this.postJson(
        `/v1beta/models/${encodeURIComponent(options.model)}:generateContent`,
        buildGeminiPayload(options),
        options,
      );
    }
    if (options.transport === "chat") {
      return this.postJson("/v1/chat/completions", buildChatPayload(options), options);
    }
    return this.postJson("/v1/images/generations", buildGenerationPayload(options), options);
  }

  async editImage(options) {
    const images = options.images || [];
    if (!images.length) throw new Error("At least one image is required for editing.");

    if (options.transport === "gemini") {
      const inlineImages = await Promise.all(images.map((image) => imageInputToInlineData(image)));
      return this.postJson(
        `/v1beta/models/${encodeURIComponent(options.model)}:generateContent`,
        buildGeminiPayload(options, inlineImages),
        options,
      );
    }

    if (options.transport === "chat") {
      const imageUrls = await Promise.all(images.map((image) => imageInputToDataUrl(image)));
      return this.postJson("/v1/chat/completions", buildChatPayload(options, imageUrls), options);
    }

    const materializedImages = await Promise.all(images.map((image) => materializeMultipartImage(image)));
    return this.editImages({
      fields: buildEditFields(options),
      images: materializedImages,
      timeoutMs: options.timeoutMs,
    });
  }

  async createImageGenerationTask(payload) {
    return this.postJson("/v1/image-tasks/generations", payload);
  }

  async createImageEditTask(payload) {
    return this.postJson("/v1/image-tasks/edits", payload);
  }

  async editImages(payload) {
    const form = new MultipartFormData();

    for (const [key, value] of Object.entries(payload.fields || {})) {
      if (value !== undefined && value !== null && value !== "") {
        form.append(key, String(value));
      }
    }

    for (const file of payload.images || []) {
      await appendFileInput(form, "image", file, "image.png");
    }

    if (payload.mask) {
      await appendFileInput(form, "mask", payload.mask, "mask.png");
    }

    return postMultipartJson(`${this.config.baseUrl}/v1/images/edits`, form, {
      Authorization: `Bearer ${this.config.apiKey}`,
    }, payload.timeoutMs || this.config.timeoutMs);
  }

  async getImageTask(taskId, { detail = true } = {}) {
    const suffix = detail ? "?detail=true" : "";
    return this.getJson(`/v1/image-tasks/${encodeURIComponent(taskId)}${suffix}`);
  }

  async waitForImageTask(taskId, options = {}) {
    const pollIntervalMs = options.pollIntervalMs ?? this.config.pollIntervalMs;
    const timeoutMs = options.timeoutMs ?? this.config.timeoutMs;
    const started = Date.now();
    let lastTask;

    while (Date.now() - started <= timeoutMs) {
      lastTask = await this.getImageTask(taskId, { detail: true });
      if (TERMINAL_STATUSES.has(lastTask.status)) return lastTask;
      await sleep(pollIntervalMs);
    }

    const status = lastTask?.status ? ` Last status: ${lastTask.status}.` : "";
    throw new Error(`Timed out waiting for image task ${taskId}.${status}`);
  }

  async generateImageAsync(payload, options = {}) {
    const task = await this.createImageGenerationTask(payload);
    const taskId = task.task_id || task.id;
    if (!taskId) {
      throw new Error(`APINebula did not return a task id: ${JSON.stringify(task)}`);
    }
    const finalTask = options.wait === false ? task : await this.waitForImageTask(taskId, options);
    return { taskId, task, finalTask };
  }

  async editImageAsync(payload, options = {}) {
    const task = await this.createImageEditTask(payload);
    const taskId = task.task_id || task.id;
    if (!taskId) {
      throw new Error(`APINebula did not return a task id: ${JSON.stringify(task)}`);
    }
    const finalTask = options.wait === false ? task : await this.waitForImageTask(taskId, options);
    return { taskId, task, finalTask };
  }

  async postJson(pathname, payload, options = {}) {
    const response = await fetch(`${this.config.baseUrl}${pathname}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.config.apiKey}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: stringifyJsonForRequest(payload),
      signal: timeoutSignal(options.timeoutMs || this.config.timeoutMs),
    });
    return readJsonResponse(response);
  }

  async getJson(pathname) {
    const response = await fetch(`${this.config.baseUrl}${pathname}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${this.config.apiKey}`,
      },
      signal: timeoutSignal(this.config.timeoutMs),
    });
    return readJsonResponse(response);
  }
}

export function buildGenerationPayload(options) {
  const payload = {
    model: options.model,
    prompt: options.prompt,
  };

  setIfPresent(payload, "n", options.n);
  setIfPresent(payload, "size", options.size);
  setIfPresent(payload, "quality", options.quality);
  setIfPresent(payload, "response_format", options.responseFormat);
  setIfPresent(payload, "background", options.background);
  setIfPresent(payload, "moderation", options.moderation);
  return payload;
}

export function buildGeminiPayload(options, inlineImages = []) {
  const parts = [{ text: options.prompt }];
  for (const image of inlineImages) parts.push({ inlineData: image });

  const imageConfig = {};
  setIfPresent(imageConfig, "aspectRatio", options.aspectRatio);
  setIfPresent(imageConfig, "imageSize", options.resolution);

  const generationConfig = { responseModalities: ["IMAGE"] };
  if (Object.keys(imageConfig).length) generationConfig.imageConfig = imageConfig;

  return {
    contents: [{ role: "user", parts }],
    generationConfig,
  };
}

export function buildChatPayload(options, imageUrls = []) {
  const content = imageUrls.length
    ? [
        { type: "text", text: options.prompt },
        ...imageUrls.map((url) => ({ type: "image_url", image_url: { url } })),
      ]
    : options.prompt;

  return {
    model: options.model,
    messages: [{ role: "user", content }],
    stream: false,
  };
}

export function buildEditTaskPayload(options) {
  const payload = {
    model: options.model,
    prompt: options.prompt,
    images: (options.imageUrls || []).map((imageUrl) => ({ image_url: imageUrl })),
  };

  setIfPresent(payload, "size", options.size);
  setIfPresent(payload, "quality", options.quality);
  setIfPresent(payload, "response_format", options.responseFormat);
  return payload;
}

export function buildEditFields(options) {
  const fields = {
    model: options.model,
    prompt: options.prompt,
  };

  setIfPresent(fields, "n", options.n);
  setIfPresent(fields, "size", options.size);
  setIfPresent(fields, "quality", options.quality);
  setIfPresent(fields, "response_format", options.responseFormat);
  setIfPresent(fields, "input_fidelity", options.inputFidelity);
  setIfPresent(fields, "background", options.background);
  setIfPresent(fields, "moderation", options.moderation);
  return fields;
}

export function stringifyJsonForRequest(value) {
  return JSON.stringify(value).replace(/[^\x20-\x7E]/g, (char) => {
    const code = char.charCodeAt(0).toString(16).padStart(4, "0");
    return `\\u${code}`;
  });
}

export function extractImageUrls(response) {
  const urls = [];
  const candidates = [
    response?.url,
    response?.image_url,
    response?.download_url,
    ...(Array.isArray(response?.data) ? response.data : []),
    ...(Array.isArray(response?.detail?.data) ? response.detail.data : []),
  ];

  for (const candidate of candidates) {
    if (!candidate) continue;
    if (typeof candidate === "string" && isHttpUrl(candidate)) {
      urls.push(candidate);
      continue;
    }
    if (typeof candidate === "object") {
      for (const key of ["download_url", "url", "image_url"]) {
        if (isHttpUrl(candidate[key])) urls.push(candidate[key]);
      }
    }
  }

  for (const choice of response?.choices || []) {
    const content = choice?.message?.content;
    if (typeof content !== "string") continue;
    for (const match of content.matchAll(/!\[[^\]]*\]\((https?:\/\/[^)\s]+)\)/g)) {
      urls.push(match[1]);
    }
  }

  return [...new Set(urls)];
}

export function extractInlineImages(response) {
  const images = [];
  for (const item of response?.data || []) {
    if (typeof item?.b64_json === "string" && item.b64_json) {
      images.push({ data: item.b64_json, mimeType: item.mime_type || "image/png" });
    }
  }
  for (const candidate of response?.candidates || []) {
    for (const part of candidate?.content?.parts || []) {
      const inlineData = part?.inlineData || part?.inline_data;
      if (typeof inlineData?.data === "string" && inlineData.data) {
        images.push({ data: inlineData.data, mimeType: inlineData.mimeType || inlineData.mime_type || "image/png" });
      }
    }
  }
  return images;
}

export async function saveTaskArtifacts({ taskId, model, finalTask, outputDir, download = true, fileStem }) {
  const fallbackStem = `${new Date().toISOString().replace(/[:.]/g, "-")}-${sanitizeName(model || finalTask?.model || "image")}-${taskId}`;
  return saveImageResponseArtifacts({
    response: finalTask,
    model,
    outputDir,
    download,
    fileStem: fileStem || fallbackStem,
  });
}

export async function saveImageResponseArtifacts({ response, model, outputDir, download = true, fileStem }) {
  await ensureOutputDir(outputDir);
  const safeModel = sanitizeName(model || response?.modelVersion || response?.model || "image");
  const stem = fileStem || `${new Date().toISOString().replace(/[:.]/g, "-")}-${safeModel}`;
  const metadataPath = path.join(outputDir, `${stem}.json`);
  const imageUrls = extractImageUrls(response);
  const inlineImages = extractInlineImages(response);
  const downloadedFiles = [];
  const inspections = [];

  if (inlineImages.length && (download || !imageUrls.length)) {
    for (let index = 0; index < inlineImages.length; index += 1) {
      const item = inlineImages[index];
      const buffer = Buffer.from(item.data, "base64");
      const inspection = inspectImageBuffer(buffer);
      const filePath = path.join(outputDir, artifactFilename(stem, index, inlineImages.length, fileStem, inspection.extension));
      await fs.promises.writeFile(filePath, buffer);
      downloadedFiles.push(filePath);
      inspections.push({ source: "inline", filePath, ...inspection });
    }
  } else if (download) {
    for (let index = 0; index < imageUrls.length; index += 1) {
      const url = imageUrls[index];
      const result = await downloadImage(url);
      const filePath = path.join(outputDir, artifactFilename(stem, index, imageUrls.length, fileStem, result.inspection.extension));
      await fs.promises.writeFile(filePath, result.buffer);
      downloadedFiles.push(filePath);
      inspections.push({ source: result.url, filePath, ...result.inspection });
    }
  }

  const metadata = omitBase64Payloads(response);
  const artifactMetadata = {
    model,
    imageUrls,
    artifacts: inspections,
  };
  metadata.jiuge_canva = artifactMetadata;
  metadata.nebula_canvas = artifactMetadata;
  await fs.promises.writeFile(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");

  return {
    metadataPath,
    imageUrls,
    downloadedFiles,
    inspections,
  };
}

export function inspectImageBuffer(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 10) throw new Error("Downloaded image is empty or truncated.");

  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    if (buffer.length < 24) throw new Error("Downloaded PNG is truncated.");
    return imageInspection("image/png", ".png", buffer.readUInt32BE(16), buffer.readUInt32BE(20), buffer.length);
  }

  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    const dimensions = jpegDimensions(buffer);
    return imageInspection("image/jpeg", ".jpg", dimensions.width, dimensions.height, buffer.length);
  }

  if (buffer.subarray(0, 6).toString("ascii") === "GIF87a" || buffer.subarray(0, 6).toString("ascii") === "GIF89a") {
    return imageInspection("image/gif", ".gif", buffer.readUInt16LE(6), buffer.readUInt16LE(8), buffer.length);
  }

  if (buffer.subarray(0, 4).toString("ascii") === "RIFF" && buffer.subarray(8, 12).toString("ascii") === "WEBP") {
    const dimensions = webpDimensions(buffer);
    return imageInspection("image/webp", ".webp", dimensions.width, dimensions.height, buffer.length);
  }

  throw new Error("Downloaded file is not a supported PNG, JPEG, WebP, or GIF image.");
}

async function readJsonResponse(response) {
  const text = await response.text();
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`APINebula returned non-JSON HTTP ${response.status}: ${text.slice(0, 500)}`);
  }

  if (!response.ok) {
    const message = json?.error?.message || json?.message || JSON.stringify(json);
    throw new Error(`APINebula HTTP ${response.status}: ${message}`);
  }
  return json;
}

async function imageInputToInlineData(image) {
  const materialized = await materializeImage(image, { requirePublicUrl: true });
  return {
    mimeType: materialized.inspection.mimeType,
    data: materialized.buffer.toString("base64"),
  };
}

async function imageInputToDataUrl(image) {
  if (image.url) {
    await validatePublicImageUrl(image.url);
    return image.url;
  }
  const inlineData = await imageInputToInlineData(image);
  return `data:${inlineData.mimeType};base64,${inlineData.data}`;
}

async function materializeMultipartImage(image) {
  if (!image.url) return image;
  const materialized = await materializeImage(image, { requirePublicUrl: true });
  return {
    buffer: materialized.buffer,
    filename: image.filename || `reference${materialized.inspection.extension}`,
    contentType: materialized.inspection.mimeType,
  };
}

async function materializeImage(image, { requirePublicUrl = false } = {}) {
  if (image.buffer) {
    return { buffer: image.buffer, inspection: inspectImageBuffer(image.buffer) };
  }
  if (image.path) {
    const buffer = await fs.promises.readFile(image.path);
    if (buffer.length > MAX_INPUT_IMAGE_BYTES) throw new Error("Reference image exceeds the 32 MB limit.");
    return { buffer, inspection: inspectImageBuffer(buffer) };
  }
  if (image.url) {
    if (requirePublicUrl) await validatePublicImageUrl(image.url);
    const result = await fetchBufferWithRedirects(image.url, {
      maxBytes: MAX_INPUT_IMAGE_BYTES,
      validateUrl: requirePublicUrl ? validatePublicImageUrl : undefined,
    });
    return { buffer: result.buffer, inspection: inspectImageBuffer(result.buffer) };
  }
  throw new Error("Image input must include a buffer, path, or URL.");
}

async function downloadImage(originalUrl) {
  const candidates = [originalUrl, fallbackCdnUrl(originalUrl)].filter(Boolean);
  let lastError;
  for (const candidate of [...new Set(candidates)]) {
    try {
      const result = await fetchBufferWithRedirects(candidate, { maxBytes: MAX_OUTPUT_IMAGE_BYTES });
      return { ...result, inspection: inspectImageBuffer(result.buffer) };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error(`Failed to download ${originalUrl}.`);
}

async function fetchBufferWithRedirects(urlString, { maxBytes, validateUrl, redirects = 4 } = {}) {
  let current = urlString;
  for (let redirect = 0; redirect <= redirects; redirect += 1) {
    await validateUrl?.(current);
    const response = await fetch(current, {
      redirect: "manual",
      signal: timeoutSignal(120000),
      headers: { Accept: "image/*" },
    });
    if (response.status >= 300 && response.status < 400 && response.headers.get("location")) {
      current = new URL(response.headers.get("location"), current).href;
      continue;
    }
    if (!response.ok) throw new Error(`Failed to download ${current}: HTTP ${response.status}`);
    const declaredLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
      throw new Error(`Image download exceeds the ${Math.round(maxBytes / 1024 / 1024)} MB limit.`);
    }
    const buffer = Buffer.from(await response.arrayBuffer());
    if (!buffer.length) throw new Error(`Downloaded image is empty: ${current}`);
    if (buffer.length > maxBytes) throw new Error(`Image download exceeds the ${Math.round(maxBytes / 1024 / 1024)} MB limit.`);
    return { buffer, url: current };
  }
  throw new Error(`Too many redirects while downloading ${urlString}.`);
}

async function validatePublicImageUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Reference image URL is invalid.");
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Reference image URL must be a public HTTP or HTTPS address.");
  }
  if (url.hostname.toLowerCase() === "localhost") throw new Error("Reference image URL must be public.");

  const addresses = net.isIP(url.hostname)
    ? [{ address: url.hostname }]
    : await dns.lookup(url.hostname, { all: true });
  if (!addresses.length || addresses.some(({ address }) => isPrivateIp(address))) {
    throw new Error("Reference image URL must not resolve to a private network.");
  }
}

function isPrivateIp(address) {
  const normalized = address.toLowerCase().replace(/^::ffff:/, "");
  if (net.isIPv4(normalized)) {
    const [a, b] = normalized.split(".").map(Number);
    return a === 0 || a === 10 || a === 127 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || a >= 224;
  }
  return normalized === "::1" || normalized === "::" || normalized.startsWith("fc") || normalized.startsWith("fd") || normalized.startsWith("fe8") || normalized.startsWith("fe9") || normalized.startsWith("fea") || normalized.startsWith("feb");
}

function fallbackCdnUrl(value) {
  try {
    const url = new URL(value);
    if (!FALLBACK_CDN_HOSTS.has(url.hostname.toLowerCase())) return "";
    url.hostname = "cdnimage2.apinebula.ai";
    return url.href;
  } catch {
    return "";
  }
}

function artifactFilename(stem, index, total, fileStem, extension) {
  const suffix = fileStem && total === 1 ? "" : `-${index + 1}`;
  return `${stem}${suffix}${extension}`;
}

function imageInspection(mimeType, extension, width, height, bytes) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new Error(`Could not read dimensions from ${mimeType} image.`);
  }
  return { mimeType, extension, width, height, bytes };
}

function jpegDimensions(buffer) {
  let offset = 2;
  const sofMarkers = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);
  while (offset + 8 < buffer.length) {
    if (buffer[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    const marker = buffer[offset + 1];
    if (sofMarkers.has(marker)) {
      return { height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) };
    }
    if (marker === 0xd8 || marker === 0xd9) {
      offset += 2;
      continue;
    }
    const length = buffer.readUInt16BE(offset + 2);
    if (length < 2) break;
    offset += 2 + length;
  }
  throw new Error("Could not read dimensions from JPEG image.");
}

function webpDimensions(buffer) {
  const kind = buffer.subarray(12, 16).toString("ascii");
  if (kind === "VP8X" && buffer.length >= 30) {
    return { width: 1 + readUInt24LE(buffer, 24), height: 1 + readUInt24LE(buffer, 27) };
  }
  if (kind === "VP8L" && buffer.length >= 25 && buffer[20] === 0x2f) {
    const bits = buffer.readUInt32LE(21);
    return { width: 1 + (bits & 0x3fff), height: 1 + ((bits >> 14) & 0x3fff) };
  }
  if (kind === "VP8 " && buffer.length >= 30 && buffer[23] === 0x9d && buffer[24] === 0x01 && buffer[25] === 0x2a) {
    return { width: buffer.readUInt16LE(26) & 0x3fff, height: buffer.readUInt16LE(28) & 0x3fff };
  }
  throw new Error("Could not read dimensions from WebP image.");
}

function readUInt24LE(buffer, offset) {
  return buffer[offset] | (buffer[offset + 1] << 8) | (buffer[offset + 2] << 16);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setIfPresent(object, key, value) {
  if (value !== undefined && value !== null && value !== "") object[key] = value;
}

function isHttpUrl(value) {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

function sanitizeName(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "image";
}

function timeoutSignal(timeoutMs) {
  return Number.isFinite(timeoutMs) && timeoutMs > 0 ? AbortSignal.timeout(timeoutMs) : undefined;
}

async function appendFileInput(form, fieldName, file, defaultFilename) {
  const filename = file.filename || (file.path ? path.basename(file.path) : defaultFilename);
  const contentType = file.contentType || (file.path ? contentTypeFromPath(file.path) : "application/octet-stream");

  if (file.buffer) {
    form.append(fieldName, file.buffer, {
      filename,
      contentType,
      knownLength: file.buffer.length,
    });
    return;
  }

  if (file.path) {
    const options = { filename, contentType };
    try {
      options.knownLength = (await fs.promises.stat(file.path)).size;
    } catch {
      // Chunked upload is valid when the local size cannot be read.
    }
    form.append(fieldName, fs.createReadStream(file.path), options);
    return;
  }
  throw new Error("Image file must include a buffer or path.");
}

async function postMultipartJson(urlString, form, headers = {}, timeoutMs) {
  const { statusCode, text } = await submitMultipartForm(urlString, form, headers, timeoutMs);
  return parseJsonResponseText(statusCode, text);
}

async function submitMultipartForm(urlString, form, headers = {}, timeoutMs) {
  const url = new URL(urlString);
  const transport = url.protocol === "https:" ? https : http;
  const requestHeaders = form.getHeaders(headers);

  try {
    requestHeaders["content-length"] = await new Promise((resolve, reject) => {
      form.getLength((error, length) => (error ? reject(error) : resolve(length)));
    });
  } catch {
    // Streams without a known length can still use chunked transfer.
  }

  return new Promise((resolve, reject) => {
    const request = transport.request(
      {
        method: "POST",
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port,
        path: `${url.pathname}${url.search}`,
        headers: requestHeaders,
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => resolve({ statusCode: response.statusCode || 0, text: Buffer.concat(chunks).toString("utf8") }));
      },
    );

    request.setTimeout(timeoutMs || 1800000, () => request.destroy(new Error(`APINebula request timed out after ${timeoutMs || 1800000} ms.`)));
    request.on("error", reject);
    form.on("error", reject);
    form.pipe(request);
  });
}

function parseJsonResponseText(statusCode, text) {
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`APINebula returned non-JSON HTTP ${statusCode}: ${text.slice(0, 500)}`);
  }
  if (statusCode < 200 || statusCode >= 300) {
    const message = json?.error?.message || json?.message || JSON.stringify(json);
    throw new Error(`APINebula HTTP ${statusCode}: ${message}`);
  }
  return json;
}

function contentTypeFromPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return ({
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
  })[ext] || "application/octet-stream";
}

function omitBase64Payloads(value, parentKey = "") {
  if (!value || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map((item) => omitBase64Payloads(item, parentKey));

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => {
      const isInlineData = key === "data" && ["inlineData", "inline_data"].includes(parentKey);
      const isBase64 = key === "b64_json" || isInlineData;
      return [key, isBase64 && typeof item === "string" ? "[omitted]" : omitBase64Payloads(item, key)];
    }),
  );
}
