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
  readonly realtimeStatus = signal<'connecting' | 'live' | 'error'>('connecting');
  readonly tanks = signal<TankSummary[]>([]);
  readonly devices = signal<DeviceSummary[]>([]);
  readonly showDeviceSetup = signal(false);
  readonly editingTankId = signal<string | null>(null);
  readonly tankNameDraft = signal('');
  readonly tankHeightDraft = signal('');
  readonly tankDiameterDraft = signal('');
  readonly tankFullPressureDraft = signal('');
  readonly savingTankId = signal<string | null>(null);
  readonly tankConfigurationError = signal<string | null>(null);
  readonly canManageTanks = computed(() =>
    ['owner', 'admin'].includes(this.context().home?.role ?? ''),
  );
  readonly capacityPreview = computed(() => {
    const heightCm = this.positiveNumber(this.tankHeightDraft());
    const diameterCm = this.positiveNumber(this.tankDiameterDraft());
    if (heightCm === null || diameterCm === null) {
      return null;
    }
    return Math.round((Math.PI * (diameterCm / 2) ** 2 * heightCm) / 10) / 100;
  });
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

  startTankConfiguration(tank: TankSummary): void {
    this.editingTankId.set(tank.tankId);
    this.tankNameDraft.set(tank.name);
    this.tankHeightDraft.set(tank.heightCm?.toString() ?? '');
    this.tankDiameterDraft.set(tank.diameterCm?.toString() ?? '');
    this.tankFullPressureDraft.set(tank.fullPressureKpa?.toString() ?? '');
    this.tankConfigurationError.set(null);
  }

  cancelTankConfiguration(): void {
    this.editingTankId.set(null);
    this.tankNameDraft.set('');
    this.tankHeightDraft.set('');
    this.tankDiameterDraft.set('');
    this.tankFullPressureDraft.set('');
    this.tankConfigurationError.set(null);
  }

  useCurrentPressureAsFull(tank: TankSummary): void {
    if (tank.pressureKpa === null || tank.pressureKpa <= 0) {
      this.tankConfigurationError.set('Todavía no hay una presión válida para calibrar el lleno.');
      return;
    }
    this.tankFullPressureDraft.set(tank.pressureKpa.toString());
    this.tankConfigurationError.set(null);
  }

  async saveTankConfiguration(tank: TankSummary): Promise<void> {
    const name = this.tankNameDraft().trim();
    if (!name) {
      this.tankConfigurationError.set('Escribe un nombre para el tanque.');
      return;
    }
    const heightCm = this.positiveNumber(this.tankHeightDraft());
    const diameterCm = this.positiveNumber(this.tankDiameterDraft());
    const fullPressureKpa = this.positiveNumber(this.tankFullPressureDraft());
    if (heightCm === null || diameterCm === null) {
      this.tankConfigurationError.set('Indica una altura y un diámetro válidos en centímetros.');
      return;
    }
    if (fullPressureKpa === null) {
      this.tankConfigurationError.set(
        'Llena el tanque y usa la presión actual, o escribe su presión de lleno.',
      );
      return;
    }

    this.savingTankId.set(tank.tankId);
    this.tankConfigurationError.set(null);
    try {
      const response = await firstValueFrom(
        this.api.updateTank(this.context().home!.id, tank.tankId, {
          name,
          heightCm,
          diameterCm,
          fullPressureKpa,
        }),
      );
      this.tanks.update((tanks) =>
        tanks.map((current) =>
          current.tankId === tank.tankId
            ? {
                ...current,
                name: response.tank.name,
                heightCm: response.tank.heightCm,
                diameterCm: response.tank.diameterCm,
                fullPressureKpa: response.tank.fullPressureKpa,
                capacityLiters: response.tank.capacityLiters,
                configurationStatus: response.tank.configurationStatus,
              }
            : current,
        ),
      );
      this.cancelTankConfiguration();
    } catch {
      this.tankConfigurationError.set('No fue posible guardar la configuración del tanque.');
    } finally {
      this.savingTankId.set(null);
    }
  }

  private positiveNumber(value: string): number | null {
    const parsed = Number(value.trim().replace(',', '.'));
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
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
