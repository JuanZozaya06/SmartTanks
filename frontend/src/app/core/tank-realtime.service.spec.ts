import { mapTankState } from './tank-realtime.service';

describe('mapTankState', () => {
  it('maps the latest Firestore reading used by the dashboard', () => {
    const updatedAt = new Date('2026-08-18T15:20:03Z');

    const state = mapTankState('smarttank-84f703123456:pressure-a', {
      deviceId: 'smarttank-84f703123456',
      sensorId: 'pressure-a',
      name: 'Tanque del patio',
      configurationStatus: 'pending',
      status: 'active',
      lowLevelPercentage: 25,
      latestReading: {
        percentage: 68.3,
        liters: 276,
        waterHeightCm: 136.6,
        pressureKpa: 13.4,
        receivedAt: { toDate: () => updatedAt },
      },
    });

    expect(state).toEqual({
      tankId: 'smarttank-84f703123456:pressure-a',
      deviceId: 'smarttank-84f703123456',
      sensorId: 'pressure-a',
      name: 'Tanque del patio',
      configurationStatus: 'pending',
      status: 'active',
      percentage: 68.3,
      liters: 276,
      waterHeightCm: 136.6,
      pressureKpa: 13.4,
      capacityLiters: null,
      lowLevelPercentage: 25,
      updatedAt,
    });
  });

  it('returns null until a tank has its first reading', () => {
    expect(mapTankState('tank_1', { name: 'Tanque principal' })).toBeNull();
  });
});
