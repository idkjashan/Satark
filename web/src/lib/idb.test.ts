import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('idb-keyval', () => ({
  get: vi.fn(),
  set: vi.fn(),
  del: vi.fn(),
  clear: vi.fn(),
}));

import { get, set, del, clear } from 'idb-keyval';
import { takeSharePayload, addHistory, getHistory, clearAllData } from './idb';

const mockGet = vi.mocked(get);
const mockSet = vi.mocked(set);
const mockDel = vi.mocked(del);
const mockClear = vi.mocked(clear);

beforeEach(() => {
  mockGet.mockReset();
  mockSet.mockReset();
  mockDel.mockReset();
  mockClear.mockReset();
});

describe('share payload flow (SW writes it, /check reads-and-deletes it once)', () => {
  it('reads the payload under share:<id> and deletes it on success', async () => {
    const payload = { title: '', text: 'Join this VIP group', url: '', files: [] };
    mockGet.mockResolvedValue(payload);

    const result = await takeSharePayload('abc123');

    expect(mockGet).toHaveBeenCalledWith('share:abc123');
    expect(mockDel).toHaveBeenCalledWith('share:abc123');
    expect(result).toEqual(payload);
  });

  it('returns undefined and never deletes when there is nothing to read (already consumed, or expired)', async () => {
    mockGet.mockResolvedValue(undefined);

    const result = await takeSharePayload('gone');

    expect(result).toBeUndefined();
    expect(mockDel).not.toHaveBeenCalled();
  });
});

describe('history: last 20, never the message', () => {
  it('prepends a new entry and keeps only the most recent 20', async () => {
    const existing = Array.from({ length: 20 }, (_, i) => ({
      date: `2026-01-${String(i + 1).padStart(2, '0')}`,
      level: 'NO_SIGNS',
      lang: 'en',
    }));
    const lastSurvivor = { ...existing[18] }; // addHistory mutates `existing` in place via unshift()
    mockGet.mockResolvedValue(existing);

    await addHistory({ date: '2026-10-03', level: 'HIGH_RISK', lang: 'en' });

    expect(mockSet).toHaveBeenCalledTimes(1);
    const [, saved] = mockSet.mock.calls[0];
    expect(saved).toHaveLength(20);
    expect(saved[0]).toMatchObject({ date: '2026-10-03', level: 'HIGH_RISK' });
    // only the original first 19 survive behind the new entry - the oldest fell off
    expect(saved.at(-1)).toMatchObject(lastSurvivor);
  });

  it('getHistory returns [] rather than undefined when nothing is stored yet', async () => {
    mockGet.mockResolvedValue(undefined);
    expect(await getHistory()).toEqual([]);
  });
});

describe('clearAllData', () => {
  it('wipes the entire idb-keyval store in one call', async () => {
    await clearAllData();
    expect(mockClear).toHaveBeenCalledTimes(1);
  });
});
