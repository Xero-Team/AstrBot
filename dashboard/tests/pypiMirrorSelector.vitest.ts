import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  testPypiIndex: vi.fn(),
  measurePypiIndexSpeed: vi.fn(),
}));

vi.mock('@/api/v1', () => ({ statsApi: api }));

import PypiMirrorSelector from '@/components/shared/PypiMirrorSelector.vue';

const CUSTOM_STORAGE_KEY = 'selectedPypiMirrorCustom';

function ok(data: Record<string, number>) {
  return { status: 200, data: { status: 'ok', message: '', data } };
}

describe('PypiMirrorSelector', () => {
  beforeEach(() => {
    api.testPypiIndex.mockReset();
    api.measurePypiIndexSpeed.mockReset();
  });

  it('offers the presets plus a custom option and emits the picked URL', async () => {
    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://pypi.org/simple' },
    });

    const radios = wrapper.findAll('input[type="radio"]');
    expect(radios).toHaveLength(6);
    expect(radios[0].attributes('value')).toBe('official');

    await radios[1].setValue(true);

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([
      'https://mirrors.aliyun.com/pypi/simple',
    ]);
    wrapper.unmount();
  });

  it('keeps a saved custom URL visible and editable', async () => {
    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://mirror.example/simple/' },
    });

    const input = wrapper.find('.pypi-mirror__custom-input input');
    expect((input.element as HTMLInputElement).value).toBe(
      'https://mirror.example/simple/',
    );

    await input.setValue('https://mirror.example/pypi/simple');

    const emitted = wrapper.emitted('update:modelValue') ?? [];
    expect(emitted.at(-1)).toEqual(['https://mirror.example/pypi/simple']);
    expect(localStorage.getItem(CUSTOM_STORAGE_KEY)).toBe(
      'https://mirror.example/pypi/simple',
    );
    wrapper.unmount();
  });

  it('reuses the remembered custom URL when the custom option is picked', async () => {
    localStorage.setItem(CUSTOM_STORAGE_KEY, 'https://custom.example/simple');
    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://pypi.org/simple' },
    });

    const radios = wrapper.findAll('input[type="radio"]');
    await radios[5].setValue(true);

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([
      'https://custom.example/simple',
    ]);
    wrapper.unmount();
  });

  it('tests only the selected source with Ctrl/Cmd and shows both results', async () => {
    api.testPypiIndex.mockResolvedValue(ok({ latency: 42.4 }));
    api.measurePypiIndexSpeed.mockResolvedValue(ok({ speed: 1.5 }));

    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://mirrors.aliyun.com/pypi/simple' },
    });

    await wrapper
      .find('.pypi-mirror__test-button')
      .trigger('click', { ctrlKey: true });
    await flushPromises();

    expect(api.testPypiIndex).toHaveBeenCalledTimes(1);
    expect(api.testPypiIndex).toHaveBeenCalledWith({
      index_url: 'https://mirrors.aliyun.com/pypi/simple',
    });
    expect(api.measurePypiIndexSpeed).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain('42ms');
    expect(wrapper.text()).toContain('1.5MB/s');
    wrapper.unmount();
  });

  it('sweeps every listed source on a plain click', async () => {
    api.testPypiIndex.mockResolvedValue(ok({ latency: 10 }));
    api.measurePypiIndexSpeed.mockResolvedValue(ok({ speed: 2 }));

    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://pypi.org/simple' },
    });

    await wrapper.find('.pypi-mirror__test-button').trigger('click');
    await flushPromises();

    expect(api.testPypiIndex).toHaveBeenCalledTimes(5);
    expect(api.measurePypiIndexSpeed).toHaveBeenCalledTimes(5);
    wrapper.unmount();
  });

  it('marks a source unavailable when its probe fails', async () => {
    api.testPypiIndex.mockRejectedValue(new Error('boom'));
    api.measurePypiIndexSpeed.mockRejectedValue(new Error('boom'));

    const wrapper = mountWithVuetify(PypiMirrorSelector, {
      props: { modelValue: 'https://pypi.org/simple' },
    });

    await wrapper
      .find('.pypi-mirror__test-button')
      .trigger('click', { ctrlKey: true });
    await flushPromises();

    expect(wrapper.text()).toContain('Unavailable');
    wrapper.unmount();
  });
});
