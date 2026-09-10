import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const root = new URL('../', import.meta.url);
const readJson = (path) =>
  JSON.parse(readFileSync(new URL(path, root), 'utf8'));

test('the complete authoritative specification package is present', () => {
  const manifest = readJson('SPEC_MANIFEST.json');
  assert.equal(manifest.files.length, 13);
  for (const { path, bytes } of manifest.files) {
    // Normalize checkout line endings; Git can materialize LF files as CRLF.
    const content = readFileSync(new URL(path, root), 'utf8').replaceAll(
      '\r\n',
      '\n',
    );
    assert.equal(Buffer.byteLength(content), bytes, path);
  }
});

test('the desktop embeds assets and restricts IPC to its local engine commands', () => {
  const config = readJson('apps/desktop/src-tauri/tauri.conf.json');
  assert.equal(config.build.devUrl, undefined);
  assert.equal(config.build.frontendDist, '../../frontend/dist');
  assert.deepEqual(config.app.security.capabilities, [
    {
      identifier: 'local-engine',
      description:
        'Only the main window can control the bundled Phase 1 engine.',
      windows: ['main'],
      permissions: [
        'allow-engine-start',
        'allow-engine-ping',
        'allow-engine-stop',
        'allow-engine-status',
      ],
    },
  ]);
  assert.match(
    config.app.security.csp,
    /connect-src ipc: http:\/\/ipc\.localhost;/u,
  );
  assert.doesNotMatch(config.app.security.csp, /https:|\*/u);
  assert.deepEqual(config.bundle.resources, {
    '../../../engine/dist/mediaqc-engine/': 'resources/engine/',
  });
  assert.equal(config.bundle.externalBin, undefined);
  assert.equal(config.bundle.active, false);
  for (const icon of config.bundle.icon) {
    assert.ok(
      existsSync(new URL(`apps/desktop/src-tauri/${icon}`, root)),
      icon,
    );
  }
});

test('dependency lockfiles are present and direct npm versions are exact', () => {
  for (const path of [
    'package-lock.json',
    'uv.lock',
    'apps/desktop/src-tauri/Cargo.lock',
  ]) {
    assert.ok(existsSync(fileURLToPath(new URL(path, root))), path);
  }
  for (const path of [
    'package.json',
    'apps/frontend/package.json',
    'apps/desktop/package.json',
  ]) {
    const manifest = readJson(path);
    for (const version of Object.values({
      ...manifest.dependencies,
      ...manifest.devDependencies,
    })) {
      assert.match(version, /^\d+\.\d+\.\d+$/u);
    }
  }
});
