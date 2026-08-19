import { mapTankState } from './tank-realtime.service';

describe('mapTankState', () => {
  it('maps the latest Firestore reading used by the dashboard', () => {
    const updatedAt = new Date('2026-08-18T15:20:03Z');

    const state = mapTankState('tank_1', {
      latestReading: {
        percentage: 68.3,
        liters: 276,
        waterHeightCm: 136.6,
        receivedAt: { toDate: () => updatedAt },
      },
    });

    expect(state).toEqual({
      tankId: 'tank_1',
      percentage: 68.3,
      liters: 276,
      waterHeightCm: 136.6,
      updatedAt,
    });
  });

  it('returns null until a tank has its first reading', () => {
    expect(mapTankState('tank_1', { name: 'Tanque principal' })).toBeNull();
  });
});
