/**
 * dev-modules: per-repo service discovery for dev-tool integrations.
 *
 * Each module drops a manifest at `<repo>/.modules/<name>/module.toml`.
 * Consumers call `installedModules()` / `isInstalled(name)` /
 * `hasCapability(name, cap)` to adapt their behavior.
 *
 * See SPEC.md for the manifest schema.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { parse as parseToml } from "smol-toml";

export const SCHEMA_VERSION = 1;

export interface ModuleInfo {
  readonly name: string;
  readonly version: string;
  readonly description: string;
  readonly capabilities: readonly string[];
  readonly config: Readonly<Record<string, unknown>>;
}

export class ManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ManifestError";
  }
}

/** Walk upward from `start` looking for a `.modules/` directory. */
export function findModulesRoot(start?: string): string | null {
  let cur = resolve(start ?? process.cwd());
  while (true) {
    const candidate = join(cur, ".modules");
    try {
      if (statSync(candidate).isDirectory()) return candidate;
    } catch {
      /* not there, keep walking */
    }
    const parent = dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

function parseManifest(
  data: Record<string, unknown>,
  expectedName: string,
): ModuleInfo {
  if (data.schema_version !== SCHEMA_VERSION) {
    throw new ManifestError(
      `unsupported schema_version ${String(
        data.schema_version,
      )} (expected ${SCHEMA_VERSION})`,
    );
  }
  const name = data.name;
  if (typeof name !== "string" || !name) {
    throw new ManifestError("missing or invalid 'name'");
  }
  if (name !== expectedName) {
    throw new ManifestError(
      `'name' field ${JSON.stringify(name)} does not match directory name ${JSON.stringify(expectedName)}`,
    );
  }
  const version = data.version;
  if (typeof version !== "string" || !version) {
    throw new ManifestError("missing or invalid 'version'");
  }
  const description =
    typeof data.description === "string" ? data.description : "";
  const capsRaw = data.capabilities;
  if (capsRaw !== undefined && !Array.isArray(capsRaw)) {
    throw new ManifestError("'capabilities' must be a list of strings");
  }
  const capabilities = Array.isArray(capsRaw)
    ? capsRaw.filter((c): c is string => typeof c === "string")
    : [];
  const configRaw = data.config;
  const config =
    configRaw && typeof configRaw === "object" && !Array.isArray(configRaw)
      ? (configRaw as Record<string, unknown>)
      : {};
  return { name, version, description, capabilities, config };
}

/** Load and validate a single module's manifest. Throws on failure. */
export function loadModule(dirPath: string): ModuleInfo {
  const raw = readFileSync(join(dirPath, "module.toml"), "utf-8");
  const data = parseToml(raw) as Record<string, unknown>;
  return parseManifest(data, basenameOf(dirPath));
}

/** Enumerate installed modules. Invalid manifests are silently skipped. */
export function installedModules(start?: string): Record<string, ModuleInfo> {
  const root = findModulesRoot(start);
  const out: Record<string, ModuleInfo> = {};
  if (!root) return out;

  let entries: string[];
  try {
    entries = readdirSync(root).sort();
  } catch {
    return out;
  }
  for (const name of entries) {
    const full = join(root, name);
    try {
      if (!statSync(full).isDirectory()) continue;
    } catch {
      continue;
    }
    try {
      const info = loadModule(full);
      out[info.name] = info;
    } catch {
      /* invalid manifest → skip */
    }
  }
  return out;
}

export function isInstalled(name: string, start?: string): boolean {
  return name in installedModules(start);
}

export function hasCapability(
  name: string,
  capability: string,
  start?: string,
): boolean {
  const info = installedModules(start)[name];
  return info !== undefined && info.capabilities.includes(capability);
}

function basenameOf(p: string): string {
  const parts = p.split(/[/\\]/);
  while (parts.length && parts[parts.length - 1] === "") parts.pop();
  return parts[parts.length - 1] ?? "";
}
