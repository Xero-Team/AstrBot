import { describe, expect, it } from 'vitest';
import {
  MAX_DOMAIN_RULES,
  boundedErrors,
  isNativePolicy,
  normalizePolicy,
  normalizeRules,
  parseRuleLines,
  requiresSandbox,
  validateDomainRule,
  validatePathRule,
  validateUnixPathRule,
} from '@/utils/localPermissionRules';
import { localPermissionDefaults } from '@/components/shared/LocalPermissionMatrix.vue';

describe('localPermissionRules', () => {
  it('parses and deduplicates non-empty lines', () => {
    expect(parseRuleLines('a.com\n\n a.com \nb.com')).toEqual([
      'a.com',
      'b.com',
    ]);
  });

  it('validates domain, path and socket rules', () => {
    expect(validateDomainRule('*.example.com:443')).toBeNull();
    expect(validateDomainRule('example.com:65536')).toMatch(/65535/);
    expect(validateDomainRule('bad host')).toMatch(/Malformed/);
    expect(validateDomainRule('[::1]:443')).toBeNull();
    expect(validateDomainRule('::1')).toBeNull();
    expect(validateDomainRule('[::::]')).toMatch(/IPv6/);
    expect(validateDomainRule('::::')).toMatch(/IPv6/);
    expect(validateDomainRule('foo::bar')).toMatch(/IPv6/);
    expect(validateDomainRule('01.2.3.4')).toMatch(/canonical/);
    expect(validateDomainRule('Example.COM')).toBeNull();
    expect(validateDomainRule('*.Example.COM.')).toBeNull();
    expect(validateDomainRule('例子.测试')).toBeNull();
    expect(validateDomainRule('bad/path.example')).toMatch(/Malformed/);
    expect(validateDomainRule('%65xample.com')).toMatch(/Malformed/);
    expect(validatePathRule('~/.ssh', 'linux')).toBeNull();
    expect(validatePathRule('/home/user@example.com/.ssh', 'linux')).toBeNull();
    expect(validatePathRule('relative/path', 'linux')).toMatch(/absolute/);
    expect(validatePathRule('/tmp/../secret', 'linux')).toMatch(/\.\./);
    expect(validatePathRule('/tmp/*.env', 'linux')).toBeNull();
    expect(validatePathRule('/tmp/new\n(deny default)', 'linux')).toMatch(
      /control/,
    );
    expect(validatePathRule('/tmp/[', 'linux')).toMatch(/unclosed/);
    expect(validateUnixPathRule('/tmp/*.sock', 'darwin')).toMatch(/literal/);
    expect(validateUnixPathRule('/tmp/api.sock', 'darwin')).toBeNull();
    expect(validateUnixPathRule('/tmp/user@host.sock', 'darwin')).toBeNull();
    expect(validatePathRule('C:\\Users\\operator\\.ssh', 'windows')).toBeNull();
    expect(validatePathRule('C:\\Users\\operator\\.ssh', 'win32')).toBeNull();
    expect(
      validatePathRule('\\\\server\\share\\operator\\.ssh', 'windows'),
    ).toBeNull();
    expect(validatePathRule('//server/share/operator', 'linux')).toMatch(
      /Windows path/,
    );
  });

  it('bounds validation errors and rule counts', () => {
    const entries = Array.from(
      { length: MAX_DOMAIN_RULES + 1 },
      (_, index) => `host${index}.example.com`,
    );
    expect(
      normalizeRules(entries, validateDomainRule, MAX_DOMAIN_RULES).rules,
    ).toHaveLength(MAX_DOMAIN_RULES);
    expect(
      boundedErrors(Array.from({ length: 40 }, (_, index) => `error-${index}`)),
    ).toHaveLength(32);
  });

  it('recognizes only the complete native tuple', () => {
    const native = normalizePolicy(undefined, localPermissionDefaults.admin);
    expect(isNativePolicy(native)).toBe(true);
    expect(requiresSandbox(native)).toBe(false);
    expect(
      requiresSandbox({
        ...native,
        filesystem: { deny_read: ['/secret'], deny_write: [] },
      }),
    ).toBe(true);
    expect(
      requiresSandbox({
        ...native,
        network: { ...native.network, allow_loopback: false },
      }),
    ).toBe(true);
  });

  it('forces network and socket coherence', () => {
    const member = normalizePolicy(
      {
        allow_execution: false,
        filesystem_scope: 'workspace',
        network: { ...localPermissionDefaults.admin.network },
        unix_sockets: { mode: 'allow_all', allowed_paths: ['/tmp/socket'] },
      },
      localPermissionDefaults.member,
    );
    expect(member.network.mode).toBe('off');
    expect(member.unix_sockets).toEqual({ mode: 'deny', allowed_paths: [] });
    const admin = normalizePolicy(
      {
        ...localPermissionDefaults.admin,
        unix_sockets: { mode: 'allow_all', allowed_paths: ['/tmp/socket'] },
      },
      localPermissionDefaults.admin,
    );
    expect(admin.unix_sockets).toEqual({
      mode: 'allow_all',
      allowed_paths: [],
    });
  });

  it('clears a stale allowlist in unrestricted mode but keeps denies', () => {
    const policy = normalizePolicy(
      {
        allow_execution: true,
        filesystem_scope: 'host',
        network: {
          ...localPermissionDefaults.admin.network,
          allowed_domains: ['stale.example'],
          denied_domains: ['blocked.example'],
        },
        unix_sockets: { mode: 'allow_all', allowed_paths: [] },
      },
      localPermissionDefaults.admin,
    );
    expect(policy.network.allowed_domains).toEqual([]);
    expect(policy.network.denied_domains).toEqual(['blocked.example']);
    expect(requiresSandbox(policy)).toBe(true);
    expect(
      isNativePolicy({
        ...policy,
        network: { ...policy.network, denied_domains: [] },
      }),
    ).toBe(true);
  });
});
