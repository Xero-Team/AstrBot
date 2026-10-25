import { describe, expect, it } from 'vitest';

import { WEBCHAT_SUBPROTOCOL, webchatProtocols } from '@/utils/webchatProtocol';

describe('webchatProtocols', () => {
  it('offers the dashboard JWT after the astrbot marker', () => {
    expect(webchatProtocols('jwt-token')).toEqual([
      WEBCHAT_SUBPROTOCOL,
      'jwt-token',
    ]);
    expect(webchatProtocols('  jwt-token  ')).toEqual([
      WEBCHAT_SUBPROTOCOL,
      'jwt-token',
    ]);
  });

  it('never offers an empty protocol when the token is missing', () => {
    expect(webchatProtocols('')).toEqual([WEBCHAT_SUBPROTOCOL]);
    expect(webchatProtocols('   ')).toEqual([WEBCHAT_SUBPROTOCOL]);
  });
});
