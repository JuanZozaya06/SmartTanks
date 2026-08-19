import { DatePipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { TankHistoryPoint, TankHistoryResponse } from '../core/models';

const CHART_WIDTH = 760;
const CHART_HEIGHT = 260;
const PLOT_LEFT = 42;
const PLOT_RIGHT = 744;
const PLOT_TOP = 18;
const PLOT_BOTTOM = 224;

function percentageValue(point: TankHistoryPoint): number | null {
  const value = point.percentage;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function buildHistoryPath(history: TankHistoryResponse): string {
  const start = Date.parse(history.from);
  const end = Date.parse(history.to);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
    return '';
  }

  let path = '';
  let previousTime: number | null = null;
  for (const point of history.points) {
    const value = percentageValue(point);
    const time = Date.parse(point.observedAt);
    if (value === null || !Number.isFinite(time)) {
      previousTime = null;
      continue;
    }
    const x = PLOT_LEFT + ((time - start) / (end - start)) * (PLOT_RIGHT - PLOT_LEFT);
    const bounded = Math.min(Math.max(value, 0), 100);
    const y = PLOT_BOTTOM - (bounded / 100) * (PLOT_BOTTOM - PLOT_TOP);
    const hasGap =
      previousTime !== null && time - previousTime > history.bucketSeconds * 1000 * 1.75;
    path += `${path && !hasGap ? ' L' : ' M'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    previousTime = time;
  }
  return path.trim();
}

@Component({
  selector: 'app-tank-history-chart',
  imports: [DatePipe],
  templateUrl: './tank-history-chart.component.html',
  styleUrl: './tank-history-chart.component.scss',
})
export class TankHistoryChartComponent {
  readonly history = input.required<TankHistoryResponse>();
  readonly timezone = input.required<string>();
  readonly path = computed(() => buildHistoryPath(this.history()));
  readonly hasEstimatedTime = computed(() =>
    this.history().points.some((point) => point.timestampQuality !== 'verified'),
  );
  readonly latestPercentage = computed(() => {
    const points = this.history().points;
    return points.length ? (points.at(-1)?.lastPercentage ?? points.at(-1)?.percentage ?? null) : null;
  });
  readonly latestLiters = computed(() => {
    const points = this.history().points;
    return points.length ? (points.at(-1)?.lastLiters ?? points.at(-1)?.liters ?? null) : null;
  });
  readonly minimumPercentage = computed(() => {
    const values = this.history().points
      .map((point) => point.minPercentage ?? point.percentage)
      .filter((value): value is number => typeof value === 'number');
    return values.length ? Math.min(...values) : null;
  });
  readonly maximumPercentage = computed(() => {
    const values = this.history().points
      .map((point) => point.maxPercentage ?? point.percentage)
      .filter((value): value is number => typeof value === 'number');
    return values.length ? Math.max(...values) : null;
  });
  readonly chartWidth = CHART_WIDTH;
  readonly chartHeight = CHART_HEIGHT;
}
