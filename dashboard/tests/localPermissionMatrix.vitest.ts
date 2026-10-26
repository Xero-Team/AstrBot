import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import LocalPermissionMatrix from '@/components/shared/LocalPermissionMatrix.vue';
import { statsApi } from '@/api/v1';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/api/v1', () => ({
  statsApi: {
    version: vi.fn().mockResolvedValue({
      data: {
        data: {
          runtime: {
            os: 'linux',
            arch: 'x64',
            sandbox: { status: 'detected', backend: 'bubblewrap' },
          },
        },
      },
    }),
  },
}));

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

function runtimeResponse(status: string, os = 'linux') {
  return {
    data: {
      data: {
        runtime: {
          os,
          arch: 'x64',
          sandbox: {
            status,
            backend: os === 'darwin' ? 'seatbelt' : 'bubblewrap',
          },
        },
      },
    },
  };
}

describe('LocalPermissionMatrix', () => {
  it('warns when a member has host-wide file access', async () => {
    const wrapper = mountWithVuetify(LocalPermissionMatrix, {
      props: {
        modelValue: {
          member: {
            filesystem_scope: 'host',
            allow_execution: false,
            network: {
              mode: 'off',
              allowed_domains: [],
              denied_domains: [],
              allow_private_network: false,
              allow_loopback: false,
            },
            filesystem: { deny_read: [], deny_write: [] },
            unix_sockets: { mode: 'deny', allowed_paths: [] },
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain(
      'Members have network access or file access across the entire environment.',
    );
  });

  it.each(['missing', 'unavailable', 'unsupported'])(
    'marks restricted execution inactive when isolation is %s',
    async (status) => {
      vi.mocked(statsApi.version).mockResolvedValueOnce(
        runtimeResponse(status) as never,
      );
      const wrapper = mountWithVuetify(LocalPermissionMatrix, {
        props: {
          modelValue: { member: restrictedMember },
        },
      });
      await flushPromises();
      expect(wrapper.text()).toContain('Inactive');
    },
  );

  it('keeps native execution active when isolation is unavailable', async () => {
    vi.mocked(statsApi.version).mockResolvedValueOnce(
      runtimeResponse('unavailable') as never,
    );
    const wrapper = mountWithVuetify(LocalPermissionMatrix, {
      props: {
        modelValue: {
          admin: {
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
          },
        },
      },
    });
    await flushPromises();
    expect(wrapper.text()).not.toContain('Inactive');
    expect(wrapper.text()).toContain('Native execution is selected');
  });
});
