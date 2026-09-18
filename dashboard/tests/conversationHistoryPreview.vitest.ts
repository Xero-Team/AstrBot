import { describe, expect, it } from 'vitest';
import ConversationHistoryPreview from '@/components/conversation/ConversationHistoryPreview.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('ConversationHistoryPreview', () => {
  it('sanitizes markdown HTML and uses a data attribute for font size', () => {
    const wrapper = mountWithVuetify(ConversationHistoryPreview, {
      props: {
        messages: [
          {
            role: 'assistant',
            content:
              '<script>alert(1)</script> ![xss](javascript:alert(1)) **ok**',
          },
        ],
      },
    });

    const preview = wrapper.get('.history-preview');
    expect(preview.attributes('style')).toBeUndefined();
    expect(preview.attributes('data-font-size')).toBe('13');
    expect(wrapper.find('script').exists()).toBe(false);
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.get('.record-markdown').html()).toContain(
      '<strong>ok</strong>',
    );
  });
});
