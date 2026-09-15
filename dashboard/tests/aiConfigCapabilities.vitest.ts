import { describe, expect, it, vi } from 'vitest';
import AiConfigPanel from '@/components/config/AiConfigPanel.vue';
import { initI18n } from '@/i18n/composables';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    name: 'VueMonacoEditor',
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

function buildMetadata(includeBtw: boolean) {
  const metadata: Record<string, unknown> = {
    agent_runner: { items: {} },
    ai: { items: {} },
    persona: { items: {} },
    knowledgebase: { description: 'Knowledge Base', items: {} },
    websearch: { description: 'Web Search', items: {} },
    agent_computer_use: { description: 'Computer Use', items: {} },
    proactive_capability: { description: 'Proactive Agent', items: {} },
    others: { items: {} },
  };
  if (includeBtw) {
    metadata.btw = {
      description: 'BTW dual loops',
      type: 'object',
      items: {
        'btw.enabled': { description: 'Enable BTW dual loops', type: 'bool' },
      },
    };
  }
  return metadata;
}

function mountAiPanel(metadata: Record<string, unknown>) {
  return mountWithVuetify(AiConfigPanel, {
    props: {
      metadata,
      configData: {
        provider_settings: { enable: true },
        agent_runner: { runner_type: 'local' },
        btw: { enabled: false },
      },
    },
    global: {
      stubs: {
        AstrBotConfigV4: {
          props: ['metadataKey'],
          template: '<div class="v4-group">{{ metadataKey }}</div>',
        },
      },
    },
  });
}

describe('AI capabilities panel', () => {
  it('lists the BTW dual-loop group after the other capabilities', async () => {
    await initI18n('en-US');
    const wrapper = mountAiPanel(buildMetadata(true));

    const capabilitiesTab = wrapper.findAll('.ai-config-tabs__item')[2];
    expect(capabilitiesTab?.text()).toBe('Capabilities');
    await capabilitiesTab?.trigger('click');

    expect(wrapper.findAll('.v4-group').map((group) => group.text())).toEqual([
      'knowledgebase',
      'websearch',
      'agent_computer_use',
      'proactive_capability',
      'btw',
    ]);
  });

  it('omits the BTW group when the panel metadata does not carry it', async () => {
    await initI18n('en-US');
    const wrapper = mountAiPanel(buildMetadata(false));

    await wrapper.findAll('.ai-config-tabs__item')[2]?.trigger('click');

    expect(wrapper.findAll('.v4-group').map((group) => group.text())).toEqual([
      'knowledgebase',
      'websearch',
      'agent_computer_use',
      'proactive_capability',
    ]);
  });
});
