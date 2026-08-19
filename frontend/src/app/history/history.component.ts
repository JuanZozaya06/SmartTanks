import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { AppSessionService } from '../core/app-session.service';
import { AuthService } from '../core/auth.service';
import { HistoryPeriod, TankHistoryResponse } from '../core/models';
import { RealtimeTankState, TankRealtimeService } from '../core/tank-realtime.service';
import { TankHistoryChartComponent } from '../dashboard/tank-history-chart.component';

@Component({
  selector: 'app-history',
  imports: [DatePipe, RouterLink, TankHistoryChartComponent],
  templateUrl: './history.component.html',
  styleUrls: ['../app.component.scss', './history.component.scss'],
})
export class HistoryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly session = inject(AppSessionService);
  private readonly realtime = inject(TankRealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private tankUnsubscriber?: () => void;
  private refreshTimer?: ReturnType<typeof setTimeout>;
  private requestId = 0;

  readonly context = computed(() => this.session.context()!);
  readonly tanks = signal<RealtimeTankState[]>([]);
  readonly realtimeStatus = signal<'connecting' | 'live' | 'error'>('connecting');
  readonly period = signal<HistoryPeriod>('day');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly updatedAt = signal<Date | null>(null);
  readonly historyByTank = signal<Record<string, TankHistoryResponse>>({});

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.tankUnsubscriber?.();
      if (this.refreshTimer) {
        clearTimeout(this.refreshTimer);
      }
    });
  }

  ngOnInit(): void {
    const homeId = this.context().home?.id;
    if (!homeId) {
      return;
    }
    this.tankUnsubscriber = this.realtime.listen(
      homeId,
      (tanks) => {
        this.tanks.set(tanks);
        this.realtimeStatus.set('live');
        this.scheduleRefresh();
      },
      () => this.realtimeStatus.set('error'),
    );
  }

  selectPeriod(period: HistoryPeriod): void {
    this.period.set(period);
    void this.refresh();
  }

  historyForTank(tankId: string): TankHistoryResponse | null {
    return this.historyByTank()[tankId] ?? null;
  }

  async refresh(): Promise<void> {
    const tanks = this.tanks();
    const currentRequest = ++this.requestId;
    if (!tanks.length) {
      this.historyByTank.set({});
      this.loading.set(false);
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    try {
      const entries = await Promise.all(
        tanks.map(async (tank) => [
          tank.tankId,
          await firstValueFrom(this.api.tankHistory(tank.tankId, this.period())),
        ] as const),
      );
      if (currentRequest === this.requestId) {
        this.historyByTank.set(Object.fromEntries(entries));
        this.updatedAt.set(new Date());
      }
    } catch {
      if (currentRequest === this.requestId) {
        this.error.set('No fue posible cargar el comportamiento de los tanques.');
      }
    } finally {
      if (currentRequest === this.requestId) {
        this.loading.set(false);
      }
    }
  }

  async logout(): Promise<void> {
    await this.auth.logout();
  }

  private scheduleRefresh(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }
    this.refreshTimer = setTimeout(() => void this.refresh(), 300);
  }
}
