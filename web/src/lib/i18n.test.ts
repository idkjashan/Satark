import { describe, it, expect } from 'vitest';
import { resolveKey, interpolate } from './i18n';

describe('resolveKey: current language -> English -> the key itself', () => {
  const dicts = {
    en: { 'ui.hello': 'Hello', 'ui.only_in_english': 'Only in English' },
    hi: { 'ui.hello': 'नमस्ते' },
  };

  it('prefers the current language when present', () => {
    expect(resolveKey(dicts, 'hi', 'ui.hello')).toBe('नमस्ते');
  });

  it('falls back to English when the key is missing in the current language', () => {
    expect(resolveKey(dicts, 'hi', 'ui.only_in_english')).toBe('Only in English');
  });

  it('falls back to the key itself when missing everywhere (never crashes, never blank)', () => {
    expect(resolveKey(dicts, 'hi', 'ui.does_not_exist')).toBe('ui.does_not_exist');
  });

  it('falls back to the key itself for a language with no dictionary at all', () => {
    expect(resolveKey(dicts, 'ta', 'ui.does_not_exist')).toBe('ui.does_not_exist');
  });
});

describe('interpolate: {name} substitution', () => {
  it('fills every placeholder it has a value for', () => {
    expect(interpolate('You lost {amount}', { amount: '₹1,000' })).toBe('You lost ₹1,000');
  });

  it('leaves an unmatched placeholder untouched instead of throwing', () => {
    expect(interpolate('Hi {name}, you have {count}', { name: 'Raj' })).toBe('Hi Raj, you have {count}');
  });

  it('is a no-op without vars', () => {
    expect(interpolate('Plain text')).toBe('Plain text');
  });
});
