// Build the GoodVibes Home Assistant sidebar panel assets.
//
// The panel and icon modules are authored in ./src and bundled with esbuild into
// the integration's served directory (custom_components/goodvibes/frontend). The
// built artifacts are committed because Home Assistant installs (HACS or a manual
// copy of custom_components/) do not run a build step; this script is how they are
// regenerated, so they are never hand-edited.
//
// Usage:
//   node build.mjs            build and write the served artifacts
//   node build.mjs --check    build to memory and fail if the committed
//                             artifacts are stale (used in CI)
//
// The build is deterministic: esbuild is pinned to an exact version, output is
// not minified (so the served artifact stays reviewable and diffs cleanly), and
// each artifact is stamped with the integration version read from manifest.json.

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, '..');
const srcDir = join(here, 'src');
const outDir = join(repoRoot, 'custom_components', 'goodvibes', 'frontend');
const manifestPath = join(outDir, '..', 'manifest.json');

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const version = manifest.version ?? '0.0.0';

const ENTRIES = ['goodvibes-home-panel.js', 'goodvibes-icons.js'];

const checkOnly = process.argv.includes('--check');

function banner(name) {
  return (
    `/*! GoodVibes Home Assistant ${name} v${version}\n` +
    ` * Built from frontend/src/${name} by frontend/build.mjs — do not edit the\n` +
    ` * served artifact directly; edit the source and rebuild. */\n`
  );
}

async function buildEntry(name) {
  const result = await build({
    entryPoints: [join(srcDir, name)],
    bundle: true,
    format: 'esm',
    target: 'es2021',
    minify: false,
    legalComments: 'none',
    write: false,
    banner: { js: banner(name) },
  });
  return result.outputFiles[0].text;
}

let stale = false;
for (const name of ENTRIES) {
  const built = await buildEntry(name);
  const outPath = join(outDir, name);
  if (checkOnly) {
    let current = '';
    try {
      current = readFileSync(outPath, 'utf8');
    } catch {
      current = '';
    }
    if (current !== built) {
      stale = true;
      console.error(`Stale built artifact: ${name} (run "npm run build")`);
    } else {
      console.log(`Up to date: ${name}`);
    }
  } else {
    writeFileSync(outPath, built);
    console.log(`Built ${name} (v${version}, ${built.length} bytes)`);
  }
}

if (checkOnly && stale) {
  process.exitCode = 1;
}
