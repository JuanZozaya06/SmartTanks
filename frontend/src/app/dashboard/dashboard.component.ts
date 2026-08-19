import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { AppContext, DeviceSummary } from '../core/models';
import { RealtimeTankState, TankRealtimeService } from '../core/tank-realtime.service';
import { DeviceClaimComponent } from '../devices/device-claim.component';

interface TankSummary {
  id: string;
  name: string;
  percentage: number;
  liters: number;
  capacityLiters: number;
  levelCm: number;
  updatedAt: Date;
  lowLevelPercentage: number;
  state: 'normal' | 'low';
  hasReading: boolean;
}

@Component({
  selector: 'app-dashboard',
  imports: [DatePipe, DeviceClaimComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: '../app.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(TankRealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly tankUnsubscribers: Array<() => void> = [];

  readonly context = input.required<AppContext>();
  readonly logout = output<void>();
  readonly apiStatus = signal<'checking' | 'online' | 'offline'>('checking');
  readonly realtimeStatus = signal<'connecting' | 'live' | 'error'>('connecting');
  readonly tanks = signal<TankSummary[]>([]);
  readonly devices = signal<DeviceSummary[]>([]);
  readonly showDeviceSetup = signal(false);
  readonly combinedPercentage = computed(() => {
    const measured = this.tanks().filter((tank) => tank.hasReading);
    return measured.length
      ? Math.round(measured.reduce((total, tank) => total + tank.percentage, 0) / measured.length)
      : 0;
  });
  readonly availableLiters = computed(() =>
    Math.round(this.tanks().reduce((total, tank) => total + tank.liters, 0)),
  );

  constructor() {
    this.destroyRef.onDestroy(() => this.stopTankListeners());
  }

  ngOnInit(): void {
    const context = this.context();
    this.tanks.set(
      context.tanks.map((tank) => ({
        id: tank.id,
        name: tank.name,
        percentage: 0,
        liters: 0,
        capacityLiters: tank.capacityLiters,
        levelCm: 0,
        updatedAt: new Date(0),
        lowLevelPercentage: tank.lowLevelPercentage,
        state: 'low',
        hasReading: false,
      })),
    );

    this.api.health().subscribe({
      next: () => this.apiStatus.set('online'),
      error: () => this.apiStatus.set('offline'),
    });
    this.startTankListeners(context.home!.id, context.tanks.map((tank) => tank.id));
    void this.loadDevices(context.home!.id);
  }

  deviceClaimed(device: DeviceSummary): void {
    this.devices.update((devices) => [
      ...devices.filter((current) => current.id !== device.id),
      device,
    ]);
    this.showDeviceSetup.set(false);
  }

  private async loadDevices(homeId: string): Promise<void> {
    try {
      const response = await firstValueFrom(this.api.devices(homeId));
      this.devices.set(response.devices);
    } catch {
      this.devices.set([]);
    }
  }

  private startTankListeners(homeId: string, tankIds: string[]): void {
    const initialized = new Set<string>();
    this.realtimeStatus.set('connecting');

    for (const tankId of tankIds) {
      const unsubscribe = this.realtime.listen(
        homeId,
        tankId,
        (state) => {
          initialized.add(tankId);
          if (state) {
            this.updateTank(state);
          }
          if (initialized.size === tankIds.length) {
            this.realtimeStatus.set('live');
          }
        },
        () => this.realtimeStatus.set('error'),
      );
      this.tankUnsubscribers.push(unsubscribe);
    }
  }

  private updateTank(state: RealtimeTankState): void {
    this.tanks.update((tanks) =>
      tanks.map((tank) =>
        tank.id === state.tankId
          ? {
              ...tank,
              percentage: state.percentage,
              liters: state.liters,
              levelCm: state.waterHeightCm,
              updatedAt: state.updatedAt,
              state: state.percentage <= tank.lowLevelPercentage ? 'low' : 'normal',
              hasReading: true,
            }
          : tank,
      ),
    );
  }

  private stopTankListeners(): void {
    for (const unsubscribe of this.tankUnsubscribers.splice(0)) {
      unsubscribe();
    }
  }
}
