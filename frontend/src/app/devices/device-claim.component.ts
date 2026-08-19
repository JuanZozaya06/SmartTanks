import { Component, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../core/api.service';
import { DeviceSummary } from '../core/models';

@Component({
  selector: 'app-device-claim',
  imports: [ReactiveFormsModule],
  templateUrl: './device-claim.component.html',
  styleUrl: './device-claim.component.scss',
})
export class DeviceClaimComponent {
  private readonly api = inject(ApiService);
  private readonly formBuilder = inject(FormBuilder);

  readonly homeId = input.required<string>();
  readonly claimed = output<DeviceSummary>();
  readonly closed = output<void>();
  readonly claiming = signal(false);
  readonly error = signal<string | null>(null);
  readonly claimForm = this.formBuilder.nonNullable.group({
    deviceId: ['', [Validators.required, Validators.pattern(/^smarttank-[a-f0-9]{12}$/)]],
    setupPin: ['', [Validators.required, Validators.pattern(/^[0-9]{8}$/)]],
    label: ['SmartTank principal', [Validators.required, Validators.maxLength(80)]],
  });

  async claim(): Promise<void> {
    if (this.claimForm.invalid) {
      this.claimForm.markAllAsTouched();
      this.error.set('El ID o el PIN no tienen el formato esperado.');
      return;
    }
    this.claiming.set(true);
    this.error.set(null);
    try {
      const value = this.claimForm.getRawValue();
      const response = await firstValueFrom(
        this.api.claimDevice(
          this.homeId(),
          value.deviceId.trim(),
          value.setupPin.trim(),
          value.label.trim(),
        ),
      );
      this.claimed.emit(response.device);
    } catch (cause) {
      this.error.set(this.apiError(cause, 'No fue posible asociar el SmartTank.'));
    } finally {
      this.claiming.set(false);
    }
  }

  private apiError(cause: unknown, fallback: string): string {
    if (cause && typeof cause === 'object' && 'error' in cause) {
      const message = (cause as { error?: { error?: { message?: string } } }).error?.error
        ?.message;
      if (message) {
        return message;
      }
    }
    return fallback;
  }
}
