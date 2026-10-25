import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import ChatBoxRoutes from '@/router/ChatBoxRoutes';

function readSource(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8');
}

describe('low-severity Dashboard hardening', () => {
  it('marks the chatbox route as authenticated', () => {
    expect(ChatBoxRoutes.meta.requiresAuth).toBe(true);
  });

  it('defaults unknown routes to authentication and keeps public routes explicit', () => {
    const router = readSource('src/router/index.ts');
    expect(router).toContain('record.meta.requiresAuth === false');
    expect(router).toContain('explicitlyPublic');
  });

  it('does not log provider config or embedding responses', () => {
    const config = readSource('src/components/shared/AstrBotConfig.vue');
    expect(config).not.toContain('console.log(response.data.data.embedding');
    expect(config).not.toContain(
      "console.error('Error getting embedding dimensions:', error)",
    );
  });

  it('does not offer the removed sandbox runtime during onboarding', () => {
    const welcome = readSource('src/views/WelcomePage.vue');
    expect(welcome).toContain("type ComputerAccessRuntime = 'local' | 'none'");
    expect(welcome).not.toContain("value: 'sandbox'");
  });

  it('consumes WebChat step-up tokens on take', () => {
    const messages = readSource('src/composables/useMessages.ts');
    expect(messages).toContain('options.webchatStepUpTokens.value = null');
  });
});
