import { Component, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { AppContext, HomeSetupRequest } from '../core/models';

@Component({
  selector: 'app-home-setup',
  imports: [ReactiveFormsModule],
  templateUrl: './home-setup.component.html',
  styleUrl: './home-setup.component.scss',
})
export class HomeSetupComponent {
  private readonly api = inject(ApiService);
  private readonly formBuilder = inject(FormBuilder);

  readonly displayName = input<string | null>(null);
  readonly created = output<AppContext>();
  readonly logout = output<void>();
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.formBuilder.nonNullable.group({
    homeName: ['', [Validators.required, Validators.maxLength(100)]],
    timezone: [
      Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Caracas',
      Validators.required,
    ],
    tank1Name: ['Tanque principal', [Validators.required, Validators.maxLength(80)]],
    tank1Height: [null as number | null, [Validators.required, Validators.min(1)]],
    tank1Diameter: [null as number | null, [Validators.required, Validators.min(1)]],
    tank1Capacity: [null as number | null, [Validators.required, Validators.min(1)]],
    tank1LowLevel: [25, [Validators.required, Validators.min(0), Validators.max(100)]],
    tank2Name: ['Tanque auxiliar', [Validators.required, Validators.maxLength(80)]],
    tank2Height: [null as number | null, [Validators.required, Validators.min(1)]],
    tank2Diameter: [null as number | null, [Validators.required, Validators.min(1)]],
    tank2Capacity: [null as number | null, [Validators.required, Validators.min(1)]],
    tank2LowLevel: [25, [Validators.required, Validators.min(0), Validators.max(100)]],
  });

  calculateCapacity(tank: 1 | 2): void {
    const heightControl = this.form.controls[`tank${tank}Height`];
    const diameterControl = this.form.controls[`tank${tank}Diameter`];
    const height = Number(heightControl.value);
    const diameter = Number(diameterControl.value);
    if (height <= 0 || diameter <= 0) {
      this.error.set('Ingresa altura y diámetro antes de calcular la capacidad.');
      return;
    }

    const liters = (Math.PI * Math.pow(diameter / 2, 2) * height) / 1000;
    this.form.controls[`tank${tank}Capacity`].setValue(Math.round(liters * 10) / 10);
    this.error.set(null);
  }

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Completa las medidas reales de los dos tanques.');
      return;
    }

    const value = this.form.getRawValue();
    const payload: HomeSetupRequest = {
      name: value.homeName.trim(),
      timezone: value.timezone.trim(),
      displayName: this.displayName(),
      tanks: [
        {
          name: value.tank1Name.trim(),
          heightCm: Number(value.tank1Height),
          diameterCm: Number(value.tank1Diameter),
          capacityLiters: Number(value.tank1Capacity),
          lowLevelPercentage: Number(value.tank1LowLevel),
        },
        {
          name: value.tank2Name.trim(),
          heightCm: Number(value.tank2Height),
          diameterCm: Number(value.tank2Diameter),
          capacityLiters: Number(value.tank2Capacity),
          lowLevelPercentage: Number(value.tank2LowLevel),
        },
      ],
    };

    this.submitting.set(true);
    this.error.set(null);
    try {
      this.created.emit(await firstValueFrom(this.api.createHome(payload)));
    } catch (cause) {
      const message =
        cause && typeof cause === 'object' && 'error' in cause
          ? (cause as { error?: { error?: { message?: string } } }).error?.error?.message
          : null;
      this.error.set(message ?? 'No fue posible crear la casa. Intenta nuevamente.');
    } finally {
      this.submitting.set(false);
    }
  }
}
