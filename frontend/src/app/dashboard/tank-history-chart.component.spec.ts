import { TankHistoryPoint, TankHistoryResponse } from '../core/models';
import { buildHistoryMarkers, buildHistoryPath } from './tank-history-chart.component';

function history(points: TankHistoryResponse['points']): TankHistoryResponse {
  return {
    tank: {} as TankHistoryResponse['tank'],
    period: 'day',
    from: '2026-08-19T00:00:00Z',
    to: '2026-08-20T00:00:00Z',
    bucketSeconds: 300,
    sampleCount: points.length,
    skippedCount: 0,
    reconstructedTimestampCount: 0,
    points,
  };
}

describe('buildHistoryPath', () => {
  it('creates a visible marker when the period only contains one aggregated point', () => {
    const markers = buildHistoryMarkers(
      history([
        {
          observedAt: '2026-08-19T01:00:00Z',
          firstObservedAt: '2026-08-19T01:00:00Z',
          lastObservedAt: '2026-08-19T01:00:30Z',
          percentage: 80,
        } as TankHistoryPoint,
      ]),
    );

    expect(markers.length).toBe(1);
  });

  it('draws configured percentage readings', () => {
    const path = buildHistoryPath(
      history([
        {
          observedAt: '2026-08-19T01:00:00Z',
          firstObservedAt: '2026-08-19T01:00:05Z',
          lastObservedAt: '2026-08-19T01:04:35Z',
          percentage: 80,
        } as TankHistoryPoint,
        {
          observedAt: '2026-08-19T01:05:00Z',
          firstObservedAt: '2026-08-19T01:05:05Z',
          lastObservedAt: '2026-08-19T01:09:35Z',
          percentage: 70,
        } as TankHistoryPoint,
      ]),
    );

    expect(path).toContain('M');
    expect(path).toContain('L');
  });

  it('breaks the line after more than two minutes without readings', () => {
    const path = buildHistoryPath(
      history([
        {
          observedAt: '2026-08-19T01:00:00Z',
          firstObservedAt: '2026-08-19T01:00:00Z',
          lastObservedAt: '2026-08-19T01:04:30Z',
          percentage: 80,
        } as TankHistoryPoint,
        {
          observedAt: '2026-08-19T01:05:00Z',
          firstObservedAt: '2026-08-19T01:06:31Z',
          lastObservedAt: '2026-08-19T01:09:30Z',
          percentage: 70,
        } as TankHistoryPoint,
      ]),
    );

    expect(path.match(/M/g)?.length).toBe(2);
    expect(path).not.toContain('L');
  });

  it('keeps the line continuous with a gap of exactly two minutes', () => {
    const path = buildHistoryPath(
      history([
        {
          observedAt: '2026-08-19T01:00:00Z',
          firstObservedAt: '2026-08-19T01:00:00Z',
          lastObservedAt: '2026-08-19T01:03:00Z',
          percentage: 80,
        } as TankHistoryPoint,
        {
          observedAt: '2026-08-19T01:05:00Z',
          firstObservedAt: '2026-08-19T01:05:00Z',
          lastObservedAt: '2026-08-19T01:09:30Z',
          percentage: 70,
        } as TankHistoryPoint,
      ]),
    );

    expect(path).toContain('L');
  });
});
