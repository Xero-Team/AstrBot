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
  it('lists only the capability groups that stay in this panel', async () => {
    // BTW is deliberately absent: it moved to its own page under More Features,
    // because the work loop is a separate execution path with its own boundary
    // and was easy to lose among the model and agent-runner options here.
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
    ]);
  });
});
