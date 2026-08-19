import { mapTankState } from './tank-realtime.service';

describe('mapTankState', () => {
  it('maps the latest Firestore reading used by the dashboard', () => {
    const updatedAt = new Date('2026-08-18T15:20:03Z');

    const state = mapTankState('smarttank-84f703123456:pressure-a', {
      deviceId: 'smarttank-84f703123456',
      sensorId: 'pressure-a',
      name: 'Tanque del patio',
      configurationStatus: 'configured',
      status: 'active',
      heightCm: 200,
      diameterCm: 51,
      fullPressureKpa: 19.6,
      capacityLiters: 408.56,
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
      configurationStatus: 'configured',
      status: 'active',
      percentage: 68.3,
      liters: 276,
      waterHeightCm: 136.6,
      pressureKpa: 13.4,
      heightCm: 200,
      diameterCm: 51,
      fullPressureKpa: 19.6,
      capacityLiters: 408.56,
      lowLevelPercentage: 25,
      updatedAt,
    });
  });

  it('returns null until a tank has its first reading', () => {
    expect(mapTankState('tank_1', { name: 'Tanque principal' })).toBeNull();
  });

  it('replaces a technical discovery name with a friendly tank number', () => {
    const state = mapTankState('tank-a', {
      deviceId: 'smarttank-84f703123456',
      sensorId: 'pressure-a',
      name: 'Tanque pressure-a',
      configurationStatus: 'pending',
      latestReading: {
        pressureKpa: 10,
        receivedAt: { toDate: () => new Date('2026-08-19T12:00:00Z') },
      },
    });

    expect(state?.name).toBe('Tanque 1');
  });
});
