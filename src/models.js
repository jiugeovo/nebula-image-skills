const QUALITY_OPTIONS = ["auto", "low", "medium", "high"];
const IMAGE2_1K_SIZES = {
  generate: ["1024x1024"],
  "edit-sync": ["1024x1024", "1536x1024"],
  "edit-async": ["1024x1024", "1536x1024"],
};
const NANO_ASPECT_RATIOS = [
  "1:1",
  "1:4",
  "1:8",
  "2:3",
  "3:2",
  "3:4",
  "4:1",
  "4:3",
  "4:5",
  "5:4",
  "8:1",
  "9:16",
  "16:9",
  "21:9",
];

export const MODEL_PRESETS = {
  image2: {
    label: "Image 2 · 1K",
    skill: "nebula-image2-1k",
    group: "gpt-image-2-1k",
    transport: "images",
    models: ["gpt-image-2"],
    envModel: "JIUGE_CANVA_IMAGE2_MODEL",
    legacyEnvModels: ["NEBULA_CANVAS_IMAGE2_MODEL"],
    defaults: {
      model: "gpt-image-2",
      size: "1024x1024",
      quality: "medium",
      responseFormat: "url",
    },
    capabilities: {
      generate: true,
      localEdit: true,
      urlEdit: true,
      batchMax: 12,
      requestImageMax: 1,
      recommendedTimeoutMs: 120000,
      controls: {
        size: {
          modes: ["generate", "edit-sync", "edit-async"],
          options: [...new Set(Object.values(IMAGE2_1K_SIZES).flat())],
          optionsByMode: IMAGE2_1K_SIZES,
        },
        quality: { modes: ["generate", "edit-sync", "edit-async"], options: QUALITY_OPTIONS },
        resolution: { modes: [], options: [] },
        aspectRatio: { modes: [], options: [] },
        inputFidelity: { modes: ["edit-sync", "edit-async"], options: ["high"] },
      },
      note: "1K 分组不支持 2K/4K；保存后请以图片实际像素为准。",
    },
  },
  image2_4k: {
    label: "Image 2 · 4K",
    skill: "nebula-image2-4k",
    group: "image2-4k",
    transport: "images",
    models: ["gpt-image-2-4k"],
    envModel: "JIUGE_CANVA_IMAGE2_4K_MODEL",
    legacyEnvModels: ["NEBULA_CANVAS_IMAGE2_4K_MODEL"],
    defaults: {
      model: "gpt-image-2-4k",
      size: "3840x2160",
      quality: "high",
      responseFormat: "url",
    },
    capabilities: {
      generate: true,
      localEdit: true,
      urlEdit: true,
      batchMax: 10,
      requestImageMax: 10,
      recommendedTimeoutMs: 1800000,
      controls: {
        size: { modes: ["generate", "edit-sync", "edit-async"], options: ["3840x2160"], fixed: true },
        quality: { modes: ["generate", "edit-sync", "edit-async"], options: QUALITY_OPTIONS },
        resolution: { modes: [], options: [] },
        aspectRatio: { modes: [], options: [] },
        inputFidelity: { modes: ["edit-sync", "edit-async"], options: ["high"] },
      },
      note: "固定输出 3840x2160；单次请求可能需要较长时间。",
    },
  },
  nanobanana: {
    label: "Nano Banana",
    skill: "nebula-nanobanana",
    group: "nanobanana",
    transport: "gemini",
    models: [
      "gemini-3.1-flash-image",
      "gemini-3.1-flash-image-preview",
      "gemini-3-pro-image-preview",
      "gemini-2.5-flash-image",
      "gemini-2.5-flash-image-preview",
    ],
    envModel: "JIUGE_CANVA_NANOBANANA_MODEL",
    legacyEnvModels: ["NEBULA_CANVAS_NANOBANANA_MODEL"],
    defaults: {
      model: "gemini-3.1-flash-image",
      resolution: "1K",
      aspectRatio: "1:1",
    },
    capabilities: {
      generate: true,
      localEdit: true,
      urlEdit: true,
      batchMax: 12,
      requestImageMax: 1,
      recommendedTimeoutMs: 600000,
      controls: {
        size: { modes: [], options: [] },
        quality: { modes: [], options: [] },
        resolution: { modes: ["generate", "edit-sync", "edit-async"], options: ["1K", "2K", "4K"] },
        aspectRatio: { modes: ["generate", "edit-sync", "edit-async"], options: NANO_ASPECT_RATIOS },
        inputFidelity: { modes: [], options: [] },
      },
      modelCapabilities: {
        "gemini-2.5-flash-image": { resolutions: ["1K"] },
        "gemini-2.5-flash-image-preview": { resolutions: ["1K"] },
        "gemini-3.1-flash-image": { resolutions: ["1K", "2K", "4K"] },
        "gemini-3.1-flash-image-preview": { resolutions: ["1K", "2K", "4K"] },
        "gemini-3-pro-image-preview": { resolutions: ["1K", "2K", "4K"] },
      },
      note: "使用 Gemini 原生接口；2.5 Flash 仅支持 1K。",
    },
  },
  grok: {
    label: "Grok Imagine",
    skill: "nebula-grok",
    group: "Grok",
    transport: "chat",
    models: ["grok-imagine-image"],
    envModel: "JIUGE_CANVA_GROK_MODEL",
    legacyEnvModels: ["NEBULA_CANVAS_GROK_MODEL"],
    defaults: {
      model: "grok-imagine-image",
    },
    capabilities: {
      generate: true,
      localEdit: true,
      urlEdit: true,
      batchMax: 12,
      requestImageMax: 1,
      recommendedTimeoutMs: 180000,
      controls: {
        size: { modes: [], options: [] },
        quality: { modes: [], options: [] },
        resolution: { modes: [], options: [] },
        aspectRatio: { modes: [], options: [] },
        inputFidelity: { modes: [], options: [] },
      },
      note: "当前仅支持 1K；请直接在提示词中写明画面比例。",
    },
  },
};

const PRESET_ALIASES = {
  "gpt-image-2-1k": "image2",
  "image-2-1k": "image2",
  "image2-4k": "image2_4k",
  Grok: "grok",
};

export function applyPreset(kind, options, env = process.env) {
  const preset = getModelPresets(env)[normalizePresetName(kind)];
  const cleanOptions = omitEmpty(options);
  if (!preset) return cleanOptions;
  return {
    ...preset.defaults,
    ...cleanOptions,
  };
}

export function resolveImageOptions(kind, options = {}, { mode = "generate", env = process.env } = {}) {
  const presets = getModelPresets(env);
  const name = resolvePresetName(kind, options.model, presets);
  const preset = presets[name];
  if (!preset) throw new Error(`Unknown image preset: ${kind || options.model || "(missing)"}.`);

  const resolved = applyPreset(name, options, env);
  validateMode(preset, mode);
  validateModel(preset, resolved.model);
  validateControlValue(preset, "size", resolved.size, mode);
  validateControlValue(preset, "quality", resolved.quality, mode);
  validateControlValue(preset, "resolution", resolved.resolution, mode);
  validateControlValue(preset, "aspectRatio", resolved.aspectRatio, mode);
  validateControlValue(preset, "inputFidelity", resolved.inputFidelity, mode);
  validateResponseFormat(preset, resolved.responseFormat);
  validateModelResolution(preset, resolved.model, resolved.resolution);
  validateImageCount(preset, resolved.n);

  const normalizedOptions = {
    ...resolved,
    ...(resolved.n !== undefined ? { n: Number(resolved.n) } : {}),
  };

  return {
    name,
    preset,
    options: normalizedOptions,
  };
}

export function getPresetSummary(env = process.env) {
  return Object.entries(getModelPresets(env)).map(([name, preset]) => ({
    name,
    label: preset.label,
    skill: preset.skill,
    group: preset.group,
    transport: preset.transport,
    models: preset.models,
    envModel: preset.envModel,
    defaults: preset.defaults,
    capabilities: preset.capabilities,
  }));
}

export function getModelPresets(env = process.env) {
  return Object.fromEntries(
    Object.entries(MODEL_PRESETS).map(([name, preset]) => [
      name,
      withEnvDefault(
        preset,
        firstEnvValue(env, [preset.envModel, ...(preset.legacyEnvModels || [])]),
      ),
    ]),
  );
}

export function normalizePresetName(value) {
  if (!value) return "";
  return PRESET_ALIASES[value] || String(value).toLowerCase();
}

function resolvePresetName(kind, model, presets) {
  const normalized = normalizePresetName(kind);
  if (normalized && presets[normalized]) return normalized;
  if (kind) return normalized;
  if (!model) return "";
  return Object.entries(presets).find(([, preset]) =>
    preset.models.includes(model) || preset.defaults.model === model,
  )?.[0] || "";
}

function validateMode(preset, mode) {
  const capability = {
    generate: "generate",
    "edit-sync": "localEdit",
    "edit-async": "urlEdit",
  }[mode];
  if (capability && !preset.capabilities[capability]) {
    throw new Error(`${preset.label} does not support ${mode}.`);
  }
}

function validateModel(preset, model) {
  if (!model) throw new Error(`Model is required for ${preset.label}.`);
  const configuredDefault = preset.defaults.model;
  if (!preset.models.includes(model) && model !== configuredDefault) {
    throw new Error(`Model ${model} does not belong to the ${preset.group} group.`);
  }
}

function validateControlValue(preset, controlName, value, mode) {
  if (value === undefined || value === null || value === "") return;
  const control = preset.capabilities.controls[controlName];
  if (!control?.modes?.includes(mode)) {
    throw new Error(`${controlName} is not supported by ${preset.label} in ${mode} mode.`);
  }
  const supportedOptions = control.optionsByMode?.[mode] || control.options;
  if (supportedOptions?.length && !supportedOptions.includes(value)) {
    throw new Error(`${controlName}=${value} is not supported by ${preset.label}.`);
  }
}

function validateModelResolution(preset, model, resolution) {
  if (!resolution) return;
  const supported = preset.capabilities.modelCapabilities?.[model]?.resolutions;
  if (supported && !supported.includes(resolution)) {
    throw new Error(`${model} only supports ${supported.join(", ")} image resolution.`);
  }
}

function validateResponseFormat(preset, value) {
  if (value === undefined || value === null || value === "") return;
  if (preset.transport !== "images") {
    throw new Error(`responseFormat is not supported by ${preset.label}.`);
  }
}

function validateImageCount(preset, value) {
  if (value === undefined || value === null || value === "") return;
  if (preset.transport !== "images") {
    throw new Error(`n is not supported by ${preset.label}.`);
  }
  const count = Number(value);
  const maximum = preset.capabilities.requestImageMax || 1;
  if (!Number.isInteger(count) || count < 1 || count > maximum) {
    throw new Error(`n must be an integer between 1 and ${maximum} for ${preset.label}.`);
  }
}

function omitEmpty(object) {
  return Object.fromEntries(
    Object.entries(object || {}).filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    ),
  );
}

function withEnvDefault(preset, model) {
  if (!model) return preset;
  return {
    ...preset,
    models: preset.models.includes(model) ? preset.models : [model, ...preset.models],
    defaults: {
      ...preset.defaults,
      model,
    },
  };
}

function firstEnvValue(env, names) {
  return names.map((name) => env[name]).find((value) => value !== undefined && value !== "");
}
