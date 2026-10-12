/// <reference types="node" />
// Test helper: the real demo bundle (web/public/demo) read from disk.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parseBundle, type LoadedBundle, type Manifest } from "./bundle";

export const DEMO_DIR = join(__dirname, "..", "..", "public", "demo");

export function readDemoBundle(): LoadedBundle {
  const manifest: Manifest = JSON.parse(readFileSync(join(DEMO_DIR, "manifest.json"), "utf8"));
  const raw = readFileSync(join(DEMO_DIR, manifest.trials_file));
  const buffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  return parseBundle("/demo", manifest, buffer);
}
