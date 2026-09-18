import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import LocalPermissionMatrix from '@/components/shared/LocalPermissionMatrix.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/api/v1', () => ({
  statsApi: {
    version: vi.fn().mockResolvedValue({
      data: {
        data: {
          runtime: {
            os: 'linux',
            arch: 'x64',
            sandbox: { status: 'ok', backend: 'bubblewrap' },
          },
        },
      },
    }),
  },
}));

describe('LocalPermissionMatrix', () => {
  it('warns when a member has host-wide file access', async () => {
    const wrapper = mountWithVuetify(LocalPermissionMatrix, {
      props: {
        modelValue: {
          member: {
            filesystem_scope: 'host',
            allow_execution: false,
            allow_network: false,
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain(
      'Members have network access or file access across the entire environment.',
    );
  });
});
