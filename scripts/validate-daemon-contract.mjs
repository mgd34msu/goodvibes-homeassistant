#!/usr/bin/env bun
/**
 * validate-daemon-contract.mjs
 *
 * Runs the live half of docs/sdk-compatibility.md against a real daemon booted
 * from a published @pellux/goodvibes-sdk release.
 *
 * This exists because the "validated against SDK X" claim in
 * const.SDK_VALIDATED_VERSION used to be backed by nothing runnable: the
 * checklist lived only as prose, and each validation pass hand-rolled its own
 * throwaway boot script. That is how the claim sat at 1.15.0 while the daemon
 * moved to 1.17.2 across five releases without anything going red.
 *
 * It boots the daemon in a throwaway home directory on an ephemeral loopback
 * port, probes every route this integration actually consumes, checks the
 * response shapes documented in docs/sdk-compatibility.md, and stops the daemon
 * in a finally block. It never touches a running daemon and never reads or
 * writes real GoodVibes state.
 *
 * Requires bun (the daemon's HTTP transport is built on Bun.serve).
 *
 *   bun scripts/validate-daemon-contract.mjs            # validate against npm latest
 *   bun scripts/validate-daemon-contract.mjs 1.17.2     # validate against a pinned release
 *
 * Exit code 0 means every checked route and shape held.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PACKAGE = '@pellux/goodvibes-sdk';

const failures = [];
const notes = [];

function check(label, condition, detail) {
  if (condition) {
    console.log(`  ok    ${label}${detail ? `: ${detail}` : ''}`);
  } else {
    console.log(`  FAIL  ${label}${detail ? `: ${detail}` : ''}`);
    failures.push(label);
  }
}

/** Resolve the SDK version to validate against: argv, else npm's latest. */
function resolveVersion() {
  const requested = process.argv[2];
  if (requested) return requested;
  return execFileSync('npm', ['view', PACKAGE, 'version'], { encoding: 'utf8' }).trim();
}

/** The version const.py currently claims to have been validated against. */
function claimedVersion() {
  const text = readFileSync(join(REPO_ROOT, 'custom_components/goodvibes/const.py'), 'utf8');
  return text.match(/^SDK_VALIDATED_VERSION = "([^"]+)"$/m)?.[1] ?? null;
}

/** The version the vendored generated client was generated from. */
function vendoredContractVersion() {
  const text = readFileSync(
    join(REPO_ROOT, 'custom_components/goodvibes/generated_client.py'),
    'utf8',
  );
  return text.match(/^CONTRACT_VERSION: str = "([^"]+)"$/m)?.[1] ?? null;
}

const version = resolveVersion();
console.log(`Validating the daemon contract against ${PACKAGE}@${version}\n`);

const sandbox = mkdtempSync(join(tmpdir(), 'gv-ha-contract-'));
const sdkDir = join(sandbox, 'sdk');
let daemon;

try {
  console.log('== version coherence ==');
  const claimed = claimedVersion();
  const vendored = vendoredContractVersion();
  check('const.SDK_VALIDATED_VERSION matches the vendored contract', claimed === vendored,
    `claimed ${claimed}, vendored ${vendored}`);
  check('the validated version is the one being probed', claimed === version,
    `claimed ${claimed}, probing ${version}`);

  console.log('\n== installing the published SDK ==');
  writeFileSync(join(sandbox, 'package.json'), JSON.stringify({ name: 'gv-ha-contract-probe', private: true }));
  execFileSync('npm', ['install', '--prefix', sandbox, '--no-audit', '--no-fund', `${PACKAGE}@${version}`], {
    stdio: 'ignore',
  });
  const sdkRoot = join(sandbox, 'node_modules', PACKAGE);
  console.log(`  installed into ${sdkRoot}`);

  // The vendored Python client must be byte-identical to the release's own
  // generated artifact. This is the mechanical half of the contract check, and
  // unlike tests/test_generated_client_sync.py it does not need a sibling SDK
  // checkout, so it actually runs.
  console.log('\n== vendored client vs the release artifact ==');
  const upstream = readFileSync(
    join(sdkRoot, 'dist/contracts/artifacts/python/homeassistant_operator_client.py'),
  );
  const local = readFileSync(join(REPO_ROOT, 'custom_components/goodvibes/generated_client.py'));
  check('generated_client.py is byte-identical to the release artifact', upstream.equals(local),
    upstream.equals(local) ? '' : 'run: cp the release artifact over the vendored copy');

  console.log('\n== booting a daemon in an isolated home ==');
  const { bootDaemon } = await import(join(sdkRoot, 'dist/daemon.js'));
  const { ConfigManager } = await import(join(sdkRoot, 'dist/platform/config/index.js'));

  const homeDirectory = join(sandbox, 'home');
  const workingDir = join(sandbox, 'work');
  const token = `validate-${Math.random().toString(36).slice(2)}`;

  const configManager = new ConfigManager({ homeDir: homeDirectory, workingDir, surfaceRoot: 'goodvibes' });
  configManager.set('surfaces.homeassistant.enabled', true);
  daemon = await bootDaemon({ homeDirectory, workingDir, port: 0, token, configManager });
  console.log(`  daemon listening on ${daemon.url}`);

  const call = async (method, path, body) => {
    const res = await fetch(daemon.url + path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = text; }
    return { status: res.status, json };
  };
  const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

  // --- the surface the config flow validates -------------------------------
  console.log('\n== config-flow minimum surface ==');
  const status = await call('GET', '/status');
  check('GET /status returns 200', status.status === 200);
  check('GET /status reports status + version', typeof status.json?.status === 'string' && typeof status.json?.version === 'string',
    `status=${status.json?.status} version=${status.json?.version}`);
  check('GET /status reports the version under validation', status.json?.version === version,
    `reported ${status.json?.version}`);

  const unauth = await fetch(`${daemon.url}/status`, { headers: { Authorization: 'Bearer wrong-token' } });
  check('GET /status rejects a bad bearer token with 401', unauth.status === 401, `got ${unauth.status}`);

  const health = await call('GET', '/api/homeassistant/health');
  check('GET /api/homeassistant/health returns 200', health.status === 200);
  const caps = health.json?.capabilities ?? [];
  // const.REQUIRED_DAEMON_CAPABILITIES, the ones the integration hard-requires.
  for (const cap of ['conversation-stream', 'conversation-cancel']) {
    check(`health advertises required capability ${cap}`, caps.includes(cap));
  }
  // The wider set the integration reads opportunistically.
  for (const cap of ['conversation-submit-wait', 'stable-correlation', 'isolated-remote-chat-session',
    'remote-session-ttl', 'homeassistant-event-delivery']) {
    check(`health advertises ${cap}`, caps.includes(cap));
  }
  const endpoints = health.json?.endpoints ?? {};
  for (const key of ['conversation', 'stream', 'cancel', 'webhook']) {
    check(`health advertises the ${key} endpoint`, typeof endpoints[key] === 'string', endpoints[key]);
  }

  const manifest = await call('POST', '/api/channels/actions/homeassistant/homeassistant-manifest', {});
  check('manifest action returns 200', manifest.status === 200);
  check('manifest wraps its payload as result.device',
    isObj(manifest.json?.result?.device) && Array.isArray(manifest.json.result.device.identifiers),
    JSON.stringify(manifest.json?.result?.device?.identifiers));

  // --- home graph -----------------------------------------------------------
  console.log('\n== home graph ==');
  const hgStatus = await call('GET', '/api/homeassistant/home-graph/status');
  check('home-graph/status returns 200', hgStatus.status === 200);
  check('home-graph/status reports ok + counts + readiness',
    hgStatus.json?.ok === true &&
    ['sourceCount', 'nodeCount', 'edgeCount', 'issueCount'].every((k) => typeof hgStatus.json[k] === 'number') &&
    isObj(hgStatus.json.readiness),
    `readiness.state=${hgStatus.json?.readiness?.state}`);

  const hgIssues = await call('GET', '/api/homeassistant/home-graph/issues');
  check('home-graph/issues returns ok + spaceId + issues[]',
    hgIssues.json?.ok === true && typeof hgIssues.json.spaceId === 'string' && Array.isArray(hgIssues.json.issues));

  const hgSources = await call('GET', '/api/homeassistant/home-graph/sources');
  check('home-graph/sources returns a source list', hgSources.json?.ok === true && Array.isArray(hgSources.json.sources));

  const hgPages = await call('GET', '/api/homeassistant/home-graph/pages');
  check('home-graph/pages returns a page list', hgPages.json?.ok === true && Array.isArray(hgPages.json.pages));

  // The panel's automatic issue triage depends on this exact block.
  const refinement = await call('POST', '/api/homeassistant/home-graph/refinement/run', {
    triage: { minConfidence: 0.5, limit: 5, chunkSize: 5, force: false, skipIssueIds: [], reviewer: 'homeassistant:auto-triage' },
  });
  check('refinement/run accepts a triage input', refinement.status === 200);
  const triage = refinement.json?.triage;
  check('refinement/run returns a triage block', isObj(triage));
  if (isObj(triage)) {
    for (const key of ['ok', 'spaceId', 'configured', 'processed', 'skipped', 'applied', 'reviewed', 'decisions', 'remaining', 'minConfidence']) {
      check(`triage block carries ${key}`, key in triage, key === 'configured' ? `configured=${triage.configured}` : '');
    }
    check('triage.decisions is a list', Array.isArray(triage.decisions));
  }

  // --- conversation ---------------------------------------------------------
  console.log('\n== conversation ==');
  const cancel = await call('POST', '/api/homeassistant/conversation/cancel', {});
  // A 400 here is the route alive and validating input; a 404 would mean gone.
  check('conversation/cancel is served (validates input rather than 404)', cancel.status !== 404,
    `HTTP ${cancel.status}: ${JSON.stringify(cancel.json?.error ?? cancel.json).slice(0, 80)}`);

  // --- mail + calendar ------------------------------------------------------
  // These used to be informational, because the releases validated so far
  // carried invokable:false and the daemon 404'd them, so there was nothing to
  // assert. They are served now, so this asserts.
  //
  // What it checks is deliberately narrow, because this daemon is booted with
  // no mail composition and no account connected, the state of a fresh
  // machine, not a misconfiguration. So the requirement is not "these succeed";
  // it is that every answer is one this integration can CLASSIFY:
  //
  //   * a not-configured machine code  -> needs_setup
  //   * 404, or 501 NOT_INVOKABLE      -> unsupported
  //
  // and never a 503 ws-call-overloaded, which is what a self-dispatch loop
  // produced before the platform fix: a capacity answer for a routing fault,
  // which would have sent someone reading it to look at load. Anything else is
  // an answer with no home in the classifier, and it fails here rather than
  // surfacing as a calendar that claims to be ready with nothing behind it.
  console.log('\n== mail + calendar ==');
  const contract = JSON.parse(
    readFileSync(join(sdkRoot, 'dist/contracts/artifacts/operator-contract.json'), 'utf8'),
  );
  const byId = Object.fromEntries(contract.operator.methods.map((m) => [m.id, m]));
  const NOT_CONFIGURED_CODES = new Set([
    'EMAIL_NOT_CONFIGURED', 'CALENDAR_NOT_CONFIGURED', 'EMAIL_CREDENTIALS_MISSING',
  ]);
  for (const id of ['email.send', 'email.draft.create', 'email.inbox.list', 'email.inbox.read',
    'calendar.events.create', 'calendar.events.get', 'calendar.events.list']) {
    const entry = byId[id];
    check(`${id} is present in the operator contract`, Boolean(entry));
    if (!entry) continue;
    const { method, path } = entry.http;
    const probePath = path.replace(/\{[^}]+\}/g, '1');
    const res = await call(method, probePath, method === 'POST' ? {} : undefined);
    const code = typeof res.json?.code === 'string' ? res.json.code : null;
    const label = `${method} ${path} -> HTTP ${res.status}${code ? ` ${code}` : ''}`;

    check(`${id} is served (not a 404)`, res.status !== 404, label);
    check(
      `${id} never answers a routing fault as capacity`,
      !(res.status === 503 && res.json?.error === 'ws-call-overloaded'),
      label,
    );
    // An input-validation refusal (a required confirm, a missing field) is a
    // fine answer to a probe that deliberately sends nothing; it still proves
    // the request reached the verb rather than looping.
    const classifiable =
      (code && NOT_CONFIGURED_CODES.has(code))
      || (res.status === 501 && code === 'NOT_INVOKABLE')
      || res.status === 400;
    check(`${id} answers something the integration can classify`, classifiable, label);
    notes.push(`${id}: invokable=${entry.invokable}, ${label}`);
  }
} finally {
  if (daemon) await daemon.stop();
  rmSync(sandbox, { recursive: true, force: true });
  rmSync(sdkDir, { recursive: true, force: true });
}

console.log('\n== summary ==');
for (const note of notes) console.log(`  note  ${note}`);
if (failures.length > 0) {
  console.log(`\n${failures.length} check(s) FAILED:`);
  for (const f of failures) console.log(`  - ${f}`);
  process.exit(1);
}
console.log(`\nAll contract checks passed against ${PACKAGE}@${version}.`);
