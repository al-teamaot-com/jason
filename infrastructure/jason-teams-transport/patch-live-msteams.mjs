import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

const adapterSource = process.argv[2];
if (!adapterSource || !existsSync(adapterSource)) {
  throw new Error("usage: node patch-live-msteams.mjs <jason-direct-transport.mjs>");
}

const importLine =
  'import { dispatchJasonGovernedTeamsTurn as __dispatchJasonGovernedTeamsTurn } from "./jason-direct-transport.mjs";';
const patchMarker = "JASON_DIRECT_TEAMS_TRANSPORT_V1";
const dispatchAnchor =
  '  log.info("dispatching to agent", { sessionKey: route.sessionKey });\n  try {';
const replacement = `  // ${patchMarker}\n  const __jasonDirectResult = await __dispatchJasonGovernedTeamsTurn({\n    cfg,\n    context,\n    activity,\n    text,\n    senderId,\n    conversationId,\n    log,\n  });\n  if (__jasonDirectResult?.handled === true) {\n    log.info("jason-teams-transport: OpenClaw agent dispatch bypassed", {\n      finalResponses: __jasonDirectResult.finalResponses ?? 0,\n    });\n    return {\n      kind: "completed",\n      finalResponses: __jasonDirectResult.finalResponses ?? 0,\n    };\n  }\n\n  log.info("dispatching to agent", { sessionKey: route.sessionKey });\n  try {`;

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

const projectRootCandidates = [
  process.env.OPENCLAW_HOME
    ? path.join(process.env.OPENCLAW_HOME, "npm", "projects")
    : undefined,
  process.env.OPENCLAW_HOME
    ? path.join(process.env.OPENCLAW_HOME, ".openclaw", "npm", "projects")
    : undefined,
  "/home/node/.openclaw/npm/projects",
].filter(Boolean);

const projectsRoot = projectRootCandidates.find((candidate) => existsSync(candidate));
if (!projectsRoot) {
  throw new Error(
    `OpenClaw npm projects directory not found; checked: ${projectRootCandidates.join(", ")}`,
  );
}

// Search only installed Microsoft Teams project roots. Do not recursively walk
// the entire OpenClaw npm tree: other projects may contain transient or broken
// node_modules symlinks that are unrelated to the Teams transport.
const msteamsProjects = readdirSync(projectsRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && entry.name.startsWith("openclaw-msteams-"))
  .map((entry) => path.join(projectsRoot, entry.name));

const candidates = [];
for (const projectDir of msteamsProjects) {
  const distDir = path.join(projectDir, "node_modules", "@openclaw", "msteams", "dist");
  if (!existsSync(distDir)) {
    continue;
  }

  for (const name of readdirSync(distDir)) {
    if (!/^src-[^/]+\.js$/.test(name)) {
      continue;
    }
    const file = path.join(distDir, name);
    const candidateSource = readFileSync(file, "utf8");
    if (candidateSource.includes(dispatchAnchor)) {
      candidates.push(file);
    }
  }
}

if (candidates.length !== 1) {
  throw new Error(
    `expected exactly one live @openclaw/msteams dispatch bundle; found ${candidates.length}: ${candidates.join(", ")}`,
  );
}

const bundle = candidates[0];
const distDir = path.dirname(bundle);
const adapterTarget = path.join(distDir, "jason-direct-transport.mjs");
const backup = `${bundle}.pre-jason-direct-transport`;
let source = readFileSync(bundle, "utf8");
const beforeHash = sha256(source);

mkdirSync(distDir, { recursive: true });
copyFileSync(adapterSource, adapterTarget);

if (!source.includes(patchMarker)) {
  if (!source.includes(dispatchAnchor)) {
    throw new Error("live msteams dispatch anchor was not found; refusing a blind patch");
  }
  if (!source.includes(importLine)) {
    source = `${importLine}\n${source}`;
  }
  if (!existsSync(backup)) {
    copyFileSync(bundle, backup);
  }
  source = source.replace(dispatchAnchor, replacement);
  writeFileSync(bundle, source, "utf8");
}

const finalSource = readFileSync(bundle, "utf8");
if (!finalSource.includes(patchMarker)) {
  throw new Error("Jason direct Teams transport marker is absent after patch");
}
if (!finalSource.includes(importLine)) {
  throw new Error("Jason direct Teams transport import is absent after patch");
}
if (!finalSource.includes("core.channel.inbound.run")) {
  throw new Error("OpenClaw inbound dispatch call disappeared unexpectedly");
}

console.log(`PROJECTS_ROOT=${projectsRoot}`);
console.log(`MSTEAMS_PROJECTS=${msteamsProjects.join(",")}`);
console.log(`BUNDLE=${bundle}`);
console.log(`ADAPTER=${adapterTarget}`);
console.log(`BACKUP=${backup}`);
console.log(`BEFORE_SHA256=${beforeHash}`);
console.log(`AFTER_SHA256=${sha256(finalSource)}`);
console.log(`PATCH_MARKER=${patchMarker}`);
console.log("PATCH_STATUS=PASS");
