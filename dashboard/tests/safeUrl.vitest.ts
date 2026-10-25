import { describe, expect, it } from 'vitest';

import { safeHttpUrl } from '@/utils/safeUrl';

describe('safeHttpUrl', () => {
  it('returns normalized http and https URLs', () => {
    expect(safeHttpUrl('https://example.com/path')).toBe(
      'https://example.com/path',
    );
    expect(safeHttpUrl(' http://example.com ')).toBe('http://example.com/');
  });

  it('rejects non-http schemes and malformed values', () => {
    for (const value of [
      'javascript:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      'file:///etc/passwd',
      'vbscript:msgbox(1)',
      'mailto:user@example.com',
      '/relative/path',
      '',
      null,
      undefined,
      42,
      {},
    ]) {
      expect(safeHttpUrl(value)).toBeNull();
    }
  });
});
