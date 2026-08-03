#!/usr/bin/env node
import { startWebServer } from "../src/web-server.js";

const args = parseArgs(process.argv.slice(2));

if (args.help) {
  printHelp();
  process.exit(0);
}

try {
  const port = Number(
    args.port || process.env.JIUGE_CANVA_WEB_PORT || process.env.NEBULA_CANVAS_WEB_PORT || 8787,
  );
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("--port must be an integer between 1 and 65535.");
  }

  const server = await startWebServer({
    host:
      args.host ||
      process.env.JIUGE_CANVA_WEB_HOST ||
      process.env.NEBULA_CANVAS_WEB_HOST ||
      "127.0.0.1",
    port,
  });

  console.log(`Jiuge Canva web UI: http://${server.host}:${server.port}`);
  console.log(`Jiuge Canva REST API: http://${server.host}:${server.port}/api`);
} catch (error) {
  console.error(error?.message || error);
  process.exit(1);
}

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) throw new Error(`Unexpected argument: ${arg}`);
    const [key, inlineValue] = arg.slice(2).split("=", 2);
    if (key === "help") {
      result.help = true;
      continue;
    }
    const value = inlineValue ?? argv[++i];
    if (value === undefined || value.startsWith("--")) throw new Error(`Missing value for --${key}`);
    result[key] = value;
  }
  return result;
}

function printHelp() {
  console.log(`Jiuge Canva Web

Usage:
  jiuge-canva-web [--host <address>] [--port <number>]

Options:
  --host <address>  Bind address (default: 127.0.0.1)
  --port <number>   Listen port (default: 8787)
  --help            Show this help
`);
}
