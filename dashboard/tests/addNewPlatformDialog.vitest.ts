import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';
import { botApi, configRouteApi } from '@/api/v1';

function hasBlockedWarning(calls: unknown[][]) {
  return calls.some((args) =>
    args.some((arg) => String(arg).includes("'dense' is deprecated")),
  );
}

vi.mock('@/api/v1', () => ({
  botApi: {
    create: vi.fn(),
    update: vi.fn(),
  },
  configProfileApi: {
    list: vi.fn(),
    schema: vi.fn(),
    create: vi.fn(),
  },
  configRouteApi: {
    list: vi.fn(),
    upsert: vi.fn(),
    replace: vi.fn(),
  },
  fileApi: {
    tokenUrl: vi.fn((token: string) => `/api/files/${token}`),
  },
  sessionApi: {
    activeUmos: vi.fn(),
  },
}));

vi.mock('@/components/shared/AstrBotConfig.vue', () => ({
  default: {
    template: '<div class="astrbot-config-stub"></div>',
  },
}));

vi.mock('@/components/config/AstrBotCoreConfigWrapper.vue', () => ({
  default: {
    template: '<div class="astrbot-core-config-wrapper-stub"></div>',
  },
}));

vi.mock('@/views/ConfigPage.vue', () => ({
  default: {
    template: '<div class="config-page-stub"></div>',
  },
}));

vi.mock('@/components/platform/PlatformRegistrationAction.vue', () => ({
  default: {
    template: '<div class="platform-registration-action-stub"></div>',
  },
}));

vi.mock('@/components/shared/UmoDisplay.vue', () => ({
  default: {
    template: '<div class="umo-display-stub"></div>',
  },
}));

describe('AddNewPlatform dialog layout', () => {
  it('renders the platform editor inside a constrained scrollable dialog card', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const wrapper = mountWithVuetify(AddNewPlatform, {
      props: {
        show: true,
        metadata: {
          platform_group: {
            metadata: {
              platform: {
                config_template: {
                  aiocqhttp: {
                    id: 'default',
                    type: 'aiocqhttp',
                  },
                },
              },
            },
          },
        },
        configData: {},
      },
    });

    await flushPromises();

    expect(
      document.body.querySelector('.platform-dialog__card'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.platform-dialog__content'),
    ).not.toBeNull();
    expect(hasBlockedWarning(warnSpy.mock.calls)).toBe(false);

    wrapper.unmount();
  });
});

describe('AddNewPlatform route safety', () => {
  it('does not update a platform when its routes failed to load', async () => {
    vi.mocked(configRouteApi.list).mockReset();
    vi.mocked(configRouteApi.list).mockRejectedValue(new Error('routes down'));
    vi.mocked(botApi.update).mockClear();
    vi.mocked(configRouteApi.replace).mockClear();

    const wrapper = mountWithVuetify(AddNewPlatform, {
      props: {
        show: true,
        updatingMode: true,
        updatingPlatformConfig: { id: 'cfg', type: 'aiocqhttp' },
        metadata: {
          platform_group: {
            metadata: {
              platform: {
                config_template: {
                  aiocqhttp: { id: 'cfg', type: 'aiocqhttp' },
                },
              },
            },
          },
        },
        configData: {},
      },
    });
    await flushPromises();

    await (
      wrapper.vm as unknown as { updatePlatform: () => Promise<void> }
    ).updatePlatform();

    expect(botApi.update).not.toHaveBeenCalled();
    expect(configRouteApi.replace).not.toHaveBeenCalled();

    wrapper.unmount();
  });
});
