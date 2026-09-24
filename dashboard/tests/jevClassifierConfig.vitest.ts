import { describe, expect, it } from 'vitest';
import {
  isJevClassifierConfig,
  validateJevClassifierConfig,
} from '@/utils/jevClassifierConfig';

const validConfig = {
  type: 'jev_systemone',
  api_base: 'https://api.typesafe.ai',
  key: ['$TYPESAFE_API_KEY'],
  model: 'jev-latest',
  timeout: 20,
};

describe('JEV classifier configuration', () => {
  it('recognizes the JEV adapter and accepts environment key references', () => {
    expect(isJevClassifierConfig(validConfig)).toBe(true);
    expect(validateJevClassifierConfig(validConfig)).toBeNull();
  });

  it.each([
    [{ api_base: 'http://api.typesafe.ai' }, 'https'],
    [{ key: [] }, 'key'],
    [{ model: '' }, 'model'],
    [{ timeout: 0 }, 'timeout'],
  ])('rejects invalid JEV field', (changes, expected) => {
    expect(validateJevClassifierConfig({ ...validConfig, ...changes })).toBe(
      expected,
    );
  });

  it('does not impose JEV validation on other provider types', () => {
    expect(
      validateJevClassifierConfig({
        type: 'vllm_rerank',
        api_base: 'http://local',
      }),
    ).toBeNull();
  });
});
