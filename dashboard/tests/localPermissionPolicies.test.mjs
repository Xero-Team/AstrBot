import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, reactive, ref, shallowReactive } from 'vue';
import { parse } from 'vue/compiler-sfc';

function toJavaScript(source, moduleKind = ts.ModuleKind.CommonJS) {
  return ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: moduleKind,
    },
  }).outputText;
}

function loadRules() {
  const source = readFileSync(
    new URL('../src/utils/localPermissionRules.ts', import.meta.url),
    'utf8',
  );
  const module = { exports: {} };
  const wrapper = new Function('module', 'exports', toJavaScript(source));
  wrapper(module, module.exports);
  return module.exports;
}

const rules = loadRules();
const importBlock = /^import[\s\S]*?from\s+['"][^'"]+['"];\s*$/gm;

function setup(status, modelValue = {}, os = 'linux') {
  const source = readFileSync(
    new URL(
      '../src/components/shared/LocalPermissionMatrix.vue',
      import.meta.url,
    ),
    'utf8',
  );
  const { descriptor } = parse(source);
  const props = shallowReactive({ modelValue });
  let saved;
  const scope = vm.createContext({
    computed,
    reactive,
    ref,
    defineProps: () => props,
    defineEmits: () => (_event, value) => {
      saved = value;
      props.modelValue = value;
    },
    onMounted() {},
    useModuleI18n: () => ({ tm: (key) => key }),
    ...rules,
  });
  const script = toJavaScript(
    descriptor.script.content
      .replace('export const', 'const')
      .replace(importBlock, ''),
    ts.ModuleKind.None,
  );
  const setupScript = toJavaScript(
    descriptor.scriptSetup.content.replace(importBlock, ''),
    ts.ModuleKind.None,
  );
  const component = vm.runInContext(
    `${script}\n${setupScript}\n;({ policy, updatePermission, runtime, executionBlockedRoles, isolationFailureReason, permissionLocks })`,
    scope,
  );
  component.runtime.value = {
    os,
    sandbox: { status },
  };
  return {
    component,
    policy: (role) => JSON.parse(JSON.stringify(component.policy(role))),
    configured: (role) =>
      JSON.parse(JSON.stringify(component.policy(role, false))),
    saved: () => JSON.parse(JSON.stringify(saved)),
  };
}

const nativeAdmin = {
  filesystem_scope: 'host',
  allow_execution: true,
  network: {
    mode: 'unrestricted',
    allowed_domains: [],
    denied_domains: [],
    allow_private_network: true,
    allow_loopback: true,
  },
  filesystem: { deny_read: [], deny_write: [] },
  unix_sockets: { mode: 'allow_all', allowed_paths: [] },
};

const restrictedMember = {
  filesystem_scope: 'workspace',
  allow_execution: true,
  network: {
    mode: 'off',
    allowed_domains: [],
    denied_domains: [],
    allow_private_network: false,
    allow_loopback: false,
  },
  filesystem: { deny_read: [], deny_write: [] },
  unix_sockets: { mode: 'deny', allowed_paths: [] },
};

test('default effective permissions are native admin and file-only member', () => {
  for (const status of ['detected', 'missing', 'unavailable', 'unsupported']) {
    const { policy } = setup(status);
    assert.equal(policy('member').allow_execution, false);
    assert.equal(policy('member').filesystem_scope, 'workspace');
    assert.equal(policy('member').network.mode, 'off');
    assert.deepEqual(policy('admin'), nativeAdmin);
  }
});

test('unavailable isolation disables restricted execution without changing saved policy', () => {
  for (const status of ['missing', 'unavailable', 'unsupported']) {
    const { component, policy, configured } = setup(status, {
      member: restrictedMember,
    });
    assert.deepEqual(policy('member'), {
      ...restrictedMember,
      allow_execution: false,
      network: { ...restrictedMember.network, mode: 'off' },
      unix_sockets: { ...restrictedMember.unix_sockets, mode: 'deny' },
    });
    assert.deepEqual(configured('member'), restrictedMember);
    assert.deepEqual(Array.from(component.executionBlockedRoles.value), [
      'member',
    ]);
    component.runtime.value.sandbox.error = 'Probe timed out';
    assert.match(component.isolationFailureReason.value, /Probe timed out/);
    component.runtime.value.sandbox.status = 'detected';
    assert.deepEqual(policy('member'), restrictedMember);
  }
});

test('native policy bypasses unavailable isolation because it needs no sandbox', () => {
  for (const status of ['missing', 'unavailable', 'unsupported']) {
    const { policy } = setup(status, { admin: nativeAdmin });
    assert.deepEqual(policy('admin'), nativeAdmin);
  }
});

test('a saved execution grant can be unchecked while isolation is unavailable', () => {
  const { component, saved } = setup('unavailable', {
    member: restrictedMember,
  });
  component.updatePermission('member', { allow_execution: false });
  assert.equal(saved().member.allow_execution, false);
  assert.equal(saved().member.network.mode, 'off');
});

test('editing one role does not overwrite another role', () => {
  const { component, saved } = setup('detected', {
    member: restrictedMember,
    admin: nativeAdmin,
  });
  component.updatePermission('member', { filesystem_scope: 'host' });
  assert.deepEqual(saved().admin, nativeAdmin);
  assert.equal(saved().member.filesystem_scope, 'host');
  assert.equal(saved().member.network.mode, 'off');
});

test('enabling execution while isolation is unavailable keeps the grant so the native tuple can be completed', () => {
  const { component, saved } = setup('unavailable', {
    member: { ...restrictedMember, allow_execution: false },
  });
  component.updatePermission('member', { allow_execution: true });
  assert.equal(saved().member.allow_execution, true);
  assert.equal(saved().member.network.mode, 'off');
  component.updatePermission('member', {
    allow_execution: true,
    filesystem_scope: 'host',
    network: {
      ...nativeAdmin.network,
    },
    unix_sockets: { mode: 'allow_all', allowed_paths: [] },
  });
  assert.equal(saved().member.allow_execution, true);
  assert.equal(saved().member.network.mode, 'unrestricted');
});

test('network off forces socket deny and execution off forces network off', () => {
  const { component, saved } = setup('detected', { admin: nativeAdmin });
  component.updatePermission('admin', {
    network: { ...nativeAdmin.network, mode: 'off' },
  });
  assert.equal(saved().admin.network.mode, 'off');
  assert.equal(saved().admin.unix_sockets.mode, 'deny');
  component.updatePermission('admin', { allow_execution: false });
  assert.equal(saved().admin.allow_execution, false);
  assert.equal(saved().admin.network.mode, 'off');
});

test('rule validators enforce domain, path and socket bounds', () => {
  assert.equal(rules.validateDomainRule('*.example.com:443'), null);
  assert.match(
    rules.validateDomainRule('example.com:70000'),
    /between 1 and 65535/,
  );
  assert.match(rules.validateDomainRule('bad_label.example.com'), /Malformed/);
  assert.equal(rules.validatePathRule('~/.ssh', 'linux'), null);
  assert.match(rules.validatePathRule('**/.env', 'linux'), /absolute|anchor/);
  assert.match(rules.validateUnixPathRule('/tmp/*.sock', 'darwin'), /literal/);
  const parsed = rules.normalizeRules(
    ['a.com', 'a.com', 'bad host'],
    rules.validateDomainRule,
    256,
  );
  assert.deepEqual(parsed.rules, ['a.com']);
  assert.equal(parsed.errors.length, 1);
});
