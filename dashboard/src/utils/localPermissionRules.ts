export const MAX_DOMAIN_RULES = 256;
export const MAX_PATH_RULES = 256;
export const MAX_UNIX_PATHS = 64;
export const MAX_RULE_CHARACTERS = 512;
export const MAX_VALIDATION_ERRORS = 32;

export type LocalNetworkMode = 'off' | 'allowlist' | 'unrestricted';
export type LocalSocketMode = 'deny' | 'allow_all';
export type LocalFilesystemScope = 'none' | 'workspace' | 'host';
export type LocalAccess = 'read' | 'write' | 'edit';

export interface LocalNetworkPolicy {
  mode: LocalNetworkMode;
  allowed_domains: string[];
  denied_domains: string[];
  allow_private_network: boolean;
  allow_loopback: boolean;
}

export interface LocalFilesystemPolicy {
  deny_read: string[];
  deny_write: string[];
}

export interface LocalUnixSocketPolicy {
  mode: LocalSocketMode;
  allowed_paths: string[];
}

export interface PermissionPolicy {
  allow_execution: boolean;
  filesystem_scope: LocalFilesystemScope;
  network: LocalNetworkPolicy;
  filesystem: LocalFilesystemPolicy;
  unix_sockets: LocalUnixSocketPolicy;
}

const HOST_LABEL = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const IPV4 = /^(?:\d{1,3}\.){3}\d{1,3}$/;
const DRIVE_PREFIX = /^[A-Za-z]:/;

export function parseRuleLines(value: string): string[] {
  const rules: string[] = [];
  const seen = new Set<string>();
  for (const raw of String(value || '').split(/\r?\n/)) {
    const rule = raw.trim();
    if (!rule || seen.has(rule)) {
      continue;
    }
    seen.add(rule);
    rules.push(rule);
  }
  return rules;
}

function boundedRule(rule: string): string | null {
  if (rule.length > MAX_RULE_CHARACTERS) {
    return `Rules must be at most ${MAX_RULE_CHARACTERS} characters.`;
  }
  if (rule.includes('@')) {
    return 'Rules must not contain credentials.';
  }
  return null;
}

function validateHostLabels(host: string): string | null {
  if (!host || host.length > 253) {
    return 'Malformed domain rule.';
  }
  if (!host.split('.').every((label) => HOST_LABEL.test(label))) {
    return 'Malformed domain rule.';
  }
  return null;
}

function isValidIpv6Literal(host: string): boolean {
  if (!host.includes(':')) {
    return false;
  }
  try {
    const parsed = new URL(`http://[${host}]/`);
    return parsed.hostname.startsWith('[') && parsed.hostname.endsWith(']');
  } catch {
    return false;
  }
}

export function validateDomainRule(rule: string): string | null {
  const bounded = boundedRule(rule);
  if (bounded) {
    return bounded;
  }
  let host = rule;
  let port: string | null = null;
  const bracketedIpv6 = rule.startsWith('[');
  if (bracketedIpv6) {
    const closing = rule.indexOf(']');
    if (closing < 0) {
      return 'Bracketed IPv6 rules require a closing bracket.';
    }
    host = rule.slice(1, closing);
    const remainder = rule.slice(closing + 1);
    if (remainder) {
      if (!remainder.startsWith(':')) {
        return 'Unexpected text after a bracketed IPv6 address.';
      }
      port = remainder.slice(1);
    }
    if (!isValidIpv6Literal(host)) {
      return 'Malformed IPv6 address rule.';
    }
  } else if ((rule.match(/:/g) || []).length === 1) {
    [host, port] = rule.split(':');
  } else if ((rule.match(/:/g) || []).length > 1) {
    return isValidIpv6Literal(rule) ? null : 'Malformed IPv6 address rule.';
  }
  if (port !== null) {
    if (!/^\d+$/.test(port)) {
      return 'Domain rule ports must be numeric.';
    }
    const numeric = Number(port);
    if (numeric < 1 || numeric > 65535) {
      return 'Domain rule ports must be between 1 and 65535.';
    }
  }
  if (bracketedIpv6) {
    return null;
  }
  if (host === '*') {
    return null;
  }
  const wildcard = host.startsWith('*.');
  if (host.includes('*') && !wildcard) {
    return 'Only a leading `*.` wildcard is supported.';
  }
  if (wildcard) {
    host = host.slice(2);
    if (!host) {
      return 'A wildcard rule requires a domain suffix.';
    }
  }
  if (IPV4.test(host)) {
    const octetTexts = host.split('.');
    const octets = octetTexts.map(Number);
    if (octets.some((octet) => octet < 0 || octet > 255)) {
      return 'Malformed IPv4 address rule.';
    }
    if (octetTexts.some((octet) => octet.length > 1 && octet.startsWith('0'))) {
      return 'IPv4 rules must use canonical notation.';
    }
    return wildcard ? 'IP literal rules cannot use a wildcard.' : null;
  }
  return validateHostLabels(host);
}

export function validatePathRule(
  rule: string,
  platform: string,
): string | null {
  const bounded = boundedRule(rule);
  if (bounded) {
    return bounded;
  }
  if (
    [...rule].some((character) => {
      const code = character.codePointAt(0) ?? 0;
      return code < 0x20 || code === 0x7f;
    })
  ) {
    return 'Filesystem rules must not contain control characters.';
  }
  const normalized = rule.replace(/\\/g, '/');
  if (normalized.endsWith('/') && normalized !== '/') {
    return 'Filesystem rules must not end with a separator.';
  }
  if (normalized.split('/').includes('..')) {
    return 'Filesystem rules must not contain `..` components.';
  }
  const isWindows = platform === 'win32' || platform === 'windows';
  if (!isWindows) {
    if (DRIVE_PREFIX.test(normalized) || normalized.startsWith('//')) {
      return 'Filesystem rules use a Windows path on this platform.';
    }
    if (!(
      normalized.startsWith('/') ||
      normalized === '~' ||
      normalized.startsWith('~/')
    )) {
      return 'Filesystem rules must be absolute or start with `~`.';
    }
  } else if (!(
    /^[A-Za-z]:[\\/]/.test(rule) ||
    /^[\\/]{2}[^\\/]/.test(rule) ||
    rule === '~' ||
    /^~[\\/]/.test(rule)
  )) {
    return 'Filesystem rules must be absolute or start with `~`.';
  }
  let stripped = normalized;
  for (const match of normalized.matchAll(/\[([^\]]*)\]/g)) {
    const content = match[1];
    if (content.includes('[')) {
      return 'Filesystem glob rules contain nested `[`.';
    }
    if (!content || content === '!' || content === '^') {
      return 'Filesystem glob rules contain an empty character set.';
    }
  }
  stripped = stripped.replace(/\[[^\]]*\]/g, '');
  if (stripped.includes('[') || stripped.includes(']')) {
    return 'Filesystem glob rules contain an unclosed `[`.';
  }
  const wildcardIndex = normalized.search(/[*?[]/);
  if (wildcardIndex >= 0) {
    const prefix = normalized.slice(0, wildcardIndex).replace(/\/[^/]*$/, '');
    if (!prefix || prefix === '.') {
      return 'Filesystem glob rules require a literal traversal anchor.';
    }
  }
  return null;
}

export function validateUnixPathRule(
  rule: string,
  platform: string,
): string | null {
  if (/[*?[]/.test(rule)) {
    return 'Unix socket rules must be literal paths.';
  }
  return validatePathRule(rule, platform);
}

export function boundedErrors(errors: string[]): string[] {
  return errors.filter(Boolean).slice(0, MAX_VALIDATION_ERRORS);
}

export function normalizeRules(
  value: unknown,
  validator: (rule: string) => string | null,
  limit: number,
): { rules: string[]; errors: string[] } {
  const entries = Array.isArray(value) ? value : [];
  const errors: string[] = [];
  const rules: string[] = [];
  const seen = new Set<string>();
  if (entries.length > limit) {
    errors.push(`At most ${limit} rules are allowed.`);
  }
  for (const entry of entries.slice(0, limit)) {
    const rule = typeof entry === 'string' ? entry.trim() : '';
    const error = rule ? validator(rule) : 'Rules must be non-empty strings.';
    if (error) {
      errors.push(error);
      continue;
    }
    if (!seen.has(rule)) {
      seen.add(rule);
      rules.push(rule);
    }
  }
  return { rules, errors: boundedErrors(errors) };
}

export function isNativePolicy(policy: PermissionPolicy): boolean {
  return Boolean(
    policy.allow_execution &&
    policy.filesystem_scope === 'host' &&
    policy.network.mode === 'unrestricted' &&
    policy.network.allow_private_network &&
    policy.network.allow_loopback &&
    policy.network.allowed_domains.length === 0 &&
    policy.network.denied_domains.length === 0 &&
    policy.filesystem.deny_read.length === 0 &&
    policy.filesystem.deny_write.length === 0 &&
    policy.unix_sockets.mode === 'allow_all' &&
    policy.unix_sockets.allowed_paths.length === 0,
  );
}

export function requiresSandbox(policy: PermissionPolicy): boolean {
  return Boolean(policy.allow_execution && !isNativePolicy(policy));
}

export function normalizePolicy(
  value: Partial<PermissionPolicy> | undefined,
  defaults: PermissionPolicy,
): PermissionPolicy {
  const network = {
    ...defaults.network,
    ...((value?.network || {}) as Partial<LocalNetworkPolicy>),
  };
  const filesystem = {
    ...defaults.filesystem,
    ...((value?.filesystem || {}) as Partial<LocalFilesystemPolicy>),
  };
  const unixSockets = {
    ...defaults.unix_sockets,
    ...((value?.unix_sockets || {}) as Partial<LocalUnixSocketPolicy>),
  };
  const scope = ['none', 'workspace', 'host'].includes(
    String(value?.filesystem_scope),
  )
    ? (value?.filesystem_scope as LocalFilesystemScope)
    : defaults.filesystem_scope;
  const requestedExecution =
    value?.allow_execution === undefined
      ? defaults.allow_execution
      : value.allow_execution === true;
  let allowExecution = scope !== 'none' && requestedExecution;
  const modes: LocalNetworkMode[] = ['off', 'allowlist', 'unrestricted'];
  network.mode = modes.includes(network.mode)
    ? network.mode
    : defaults.network.mode;
  network.allowed_domains = Array.isArray(network.allowed_domains)
    ? network.allowed_domains.filter((entry) => typeof entry === 'string')
    : [];
  network.denied_domains = Array.isArray(network.denied_domains)
    ? network.denied_domains.filter((entry) => typeof entry === 'string')
    : [];
  if (!allowExecution) {
    network.mode = 'off';
  }
  if (network.mode === 'unrestricted') {
    network.allowed_domains = [];
  }
  if (network.mode === 'off') {
    unixSockets.mode = 'deny';
    unixSockets.allowed_paths = [];
  }
  if (unixSockets.mode === 'allow_all') {
    // The backend rejects `allow_all` combined with path rules; clear stale
    // entries when the mode changes instead of failing the whole save.
    unixSockets.allowed_paths = [];
  }
  if (scope === 'none') {
    allowExecution = false;
  }
  return {
    allow_execution: allowExecution,
    filesystem_scope: scope,
    network: {
      mode: network.mode,
      allowed_domains: network.allowed_domains,
      denied_domains: network.denied_domains,
      allow_private_network: network.allow_private_network === true,
      allow_loopback: network.allow_loopback === true,
    },
    filesystem: {
      deny_read: Array.isArray(filesystem.deny_read)
        ? filesystem.deny_read.filter((entry) => typeof entry === 'string')
        : [],
      deny_write: Array.isArray(filesystem.deny_write)
        ? filesystem.deny_write.filter((entry) => typeof entry === 'string')
        : [],
    },
    unix_sockets: {
      mode: unixSockets.mode === 'allow_all' ? 'allow_all' : 'deny',
      allowed_paths: Array.isArray(unixSockets.allowed_paths)
        ? unixSockets.allowed_paths.filter((entry) => typeof entry === 'string')
        : [],
    },
  };
}
