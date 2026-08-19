import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { AppContext, DeviceSummary } from '../core/models';
import { RealtimeTankState, TankRealtimeService } from '../core/tank-realtime.service';
import { DeviceClaimComponent } from '../devices/device-claim.component';

interface TankSummary extends RealtimeTankState {
  state: 'normal' | 'low' | 'unknown';
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
  private tankUnsubscriber?: () => void;

  readonly context = input.required<AppContext>();
  readonly logout = output<void>();
  readonly apiStatus = signal<'checking' | 'online' | 'offline'>('checking');
  readonly realtimeStatus = signal<'connecting' | 'live' | 'error'>('connecting');
  readonly tanks = signal<TankSummary[]>([]);
  readonly devices = signal<DeviceSummary[]>([]);
  readonly showDeviceSetup = signal(false);
  readonly editingTankId = signal<string | null>(null);
  readonly tankNameDraft = signal('');
  readonly savingTankId = signal<string | null>(null);
  readonly tankRenameError = signal<string | null>(null);
  readonly combinedPercentage = computed(() => {
    const measured = this.tanks().filter((tank) => tank.percentage !== null);
    return measured.length
      ? Math.round(
          measured.reduce((total, tank) => total + (tank.percentage ?? 0), 0) / measured.length,
        )
      : null;
  });
  readonly availableLiters = computed(() => {
    const measured = this.tanks().filter((tank) => tank.liters !== null);
    return measured.length
      ? Math.round(measured.reduce((total, tank) => total + (tank.liters ?? 0), 0))
      : null;
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.stopTankListeners());
  }

  ngOnInit(): void {
    const context = this.context();
    this.api.health().subscribe({
      next: () => this.apiStatus.set('online'),
      error: () => this.apiStatus.set('offline'),
    });
    this.startTankListener(context.home!.id);
    void this.loadDevices(context.home!.id);
  }

  deviceClaimed(device: DeviceSummary): void {
    this.devices.update((devices) => [
      ...devices.filter((current) => current.id !== device.id),
      device,
    ]);
    this.showDeviceSetup.set(false);
  }

  startRename(tank: TankSummary): void {
    this.editingTankId.set(tank.tankId);
    this.tankNameDraft.set(tank.name);
    this.tankRenameError.set(null);
  }

  cancelRename(): void {
    this.editingTankId.set(null);
    this.tankNameDraft.set('');
    this.tankRenameError.set(null);
  }

  async saveTankName(tank: TankSummary): Promise<void> {
    const name = this.tankNameDraft().trim();
    if (!name) {
      this.tankRenameError.set('Escribe un nombre para el tanque.');
      return;
    }

    this.savingTankId.set(tank.tankId);
    this.tankRenameError.set(null);
    try {
      await firstValueFrom(this.api.renameTank(this.context().home!.id, tank.tankId, name));
      this.tanks.update((tanks) =>
        tanks.map((current) => (current.tankId === tank.tankId ? { ...current, name } : current)),
      );
      this.cancelRename();
    } catch {
      this.tankRenameError.set('No fue posible guardar el nombre.');
    } finally {
      this.savingTankId.set(null);
    }
  }

  private async loadDevices(homeId: string): Promise<void> {
    try {
      const response = await firstValueFrom(this.api.devices(homeId));
      this.devices.set(response.devices);
    } catch {
      this.devices.set([]);
    }
  }

  private startTankListener(homeId: string): void {
    this.realtimeStatus.set('connecting');
    this.tankUnsubscriber = this.realtime.listen(
      homeId,
      (states) => {
        this.tanks.set(
          states.map((state) => ({
            ...state,
            state:
              state.percentage === null
                ? 'unknown'
                : state.percentage <= state.lowLevelPercentage
                  ? 'low'
                  : 'normal',
          })),
        );
        this.realtimeStatus.set('live');
      },
      () => this.realtimeStatus.set('error'),
    );
  }

  private stopTankListeners(): void {
    this.tankUnsubscriber?.();
    this.tankUnsubscriber = undefined;
  }
}
