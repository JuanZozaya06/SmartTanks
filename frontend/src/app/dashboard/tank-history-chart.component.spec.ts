import { TankHistoryPoint, TankHistoryResponse } from '../core/models';
import { buildHistoryPath } from './tank-history-chart.component';

function history(points: TankHistoryResponse['points']): TankHistoryResponse {
  return {
    tank: {} as TankHistoryResponse['tank'],
    period: 'day',
    from: '2026-08-19T00:00:00Z',
    to: '2026-08-20T00:00:00Z',
    bucketSeconds: 300,
    sampleCount: points.length,
    skippedCount: 0,
    points,
  };
}

describe('buildHistoryPath', () => {
  it('draws configured percentage readings', () => {
    const path = buildHistoryPath(
      history([
        { observedAt: '2026-08-19T01:00:00Z', percentage: 80 } as TankHistoryPoint,
        { observedAt: '2026-08-19T01:05:00Z', percentage: 70 } as TankHistoryPoint,
      ]),
    );

    expect(path).toContain('M');
    expect(path).toContain('L');
  });

  it('breaks the line when readings have a gap', () => {
    const path = buildHistoryPath(
      history([
        { observedAt: '2026-08-19T01:00:00Z', percentage: 80 } as TankHistoryPoint,
        { observedAt: '2026-08-19T02:00:00Z', percentage: 70 } as TankHistoryPoint,
      ]),
    );

    expect(path.match(/M/g)?.length).toBe(2);
    expect(path).not.toContain('L');
  });
});
