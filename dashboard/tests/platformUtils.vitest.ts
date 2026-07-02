import { describe, expect, it } from 'vitest';
import {
  getPlatformColor,
  getPlatformDisplayName,
  getPlatformIcon,
  getTutorialLink,
} from '@/utils/platformUtils';

describe('platformUtils', () => {
  it('exposes NapCat tutorial, icon, and display name mappings', () => {
    expect(getTutorialLink('napcat')).toBe(
      'https://docs.astrbot.app/platform/napcat.html',
    );
    expect(getPlatformDisplayName('napcat')).toBe(
      'napcat (NapCat WebSocket)',
    );
    expect(getPlatformIcon('napcat')).toBeTruthy();
    expect(getPlatformColor('napcat')).toBe('blue');
  });
});
