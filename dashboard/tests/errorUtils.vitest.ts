import { describe, expect, it } from 'vitest';
import { resolveErrorMessage } from '@/utils/errorUtils';

describe('resolveErrorMessage', () => {
  it('formats FastAPI validation detail arrays', () => {
    const message = resolveErrorMessage({
      response: {
        data: {
          detail: [
            {
              loc: ['body', 'config'],
              msg: 'Field required',
            },
          ],
        },
      },
    });

    expect(message).toBe('body.config: Field required');
  });
});
