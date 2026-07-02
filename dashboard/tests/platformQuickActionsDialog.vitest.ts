import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PlatformQuickActionsDialog from '@/components/platform/PlatformQuickActionsDialog.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  invokeActionMock: vi.fn(),
  copyToClipboardMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  botApi: {
    invokeAction: testState.invokeActionMock,
  },
}));

vi.mock('@/utils/clipboard', () => ({
  copyToClipboard: testState.copyToClipboardMock,
}));

function setNativeInputValue(
  input: HTMLInputElement | HTMLTextAreaElement,
  value: string,
) {
  input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

describe('PlatformQuickActionsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an empty-state notice when no supported actions are available', async () => {
    const wrapper = mountWithVuetify(PlatformQuickActionsDialog, {
      props: {
        modelValue: true,
        platformId: 'napcat-main',
        supportedActions: [],
      },
    });

    await flushPromises();

    expect(document.body.textContent ?? '').toContain(
      'This platform does not expose any proactive actions.',
    );
    wrapper.unmount();
  });

  it('invokes the selected action and renders a summary for the response', async () => {
    testState.invokeActionMock.mockResolvedValue({
      data: {
        message: 'Platform action completed',
        data: {
          status: 'ok',
          retcode: 0,
          message: 'done',
          data: {
            user_id: '445566',
          },
        },
      },
    });

    const wrapper = mountWithVuetify(PlatformQuickActionsDialog, {
      props: {
        modelValue: true,
        platformId: 'napcat-main',
        supportedActions: ['send_like', 'send_group_notice'],
      },
    });

    await flushPromises();

    const textInputs = document.body.querySelectorAll<HTMLInputElement>(
      'input[type="text"]',
    );
    const numberInput =
      document.body.querySelector<HTMLInputElement>('input[type="number"]');
    expect(textInputs.length).toBeGreaterThan(0);
    expect(numberInput).not.toBeNull();
    setNativeInputValue(textInputs[textInputs.length - 1], '445566');
    setNativeInputValue(numberInput!, '3');
    await flushPromises();

    const buttons = Array.from(document.body.querySelectorAll('button'));
    const runButton = buttons.find((button) =>
      button.textContent?.includes('Run action'),
    );
    expect(runButton).toBeTruthy();
    runButton!.dispatchEvent(new Event('click', { bubbles: true }));
    await flushPromises();

    expect(testState.invokeActionMock).toHaveBeenCalledWith('napcat-main', {
      action_name: 'send_like',
      payload: {
        user_id: '445566',
        times: 3,
      },
    });
    expect(document.body.textContent ?? '').toContain('Status: ok');
    expect(document.body.textContent ?? '').toContain('Retcode: 0');
    expect(document.body.textContent ?? '').toContain('Message: done');
    expect(wrapper.emitted('action-complete')).toHaveLength(1);
    expect(wrapper.emitted('show-toast')?.[0]).toEqual([
      {
        message: 'Platform action completed',
        type: 'success',
      },
    ]);
    wrapper.unmount();
  });

  it('emits an error toast when the API call fails', async () => {
    testState.invokeActionMock.mockRejectedValue(new Error('Remote failed'));

    const wrapper = mountWithVuetify(PlatformQuickActionsDialog, {
      props: {
        modelValue: true,
        platformId: 'napcat-main',
        supportedActions: ['send_like'],
      },
    });

    await flushPromises();

    const textInput =
      document.body.querySelectorAll<HTMLInputElement>('input[type="text"]');
    const numberInput =
      document.body.querySelector<HTMLInputElement>('input[type="number"]');
    setNativeInputValue(textInput[textInput.length - 1], '445566');
    setNativeInputValue(numberInput!, '2');
    await flushPromises();

    const runButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('Run action'),
    );
    runButton!.dispatchEvent(new Event('click', { bubbles: true }));
    await flushPromises();

    expect(wrapper.emitted('action-complete')).toBeUndefined();
    expect(wrapper.emitted('show-toast')?.[0]).toEqual([
      {
        message: 'Remote failed',
        type: 'error',
      },
    ]);
    wrapper.unmount();
  });
});
