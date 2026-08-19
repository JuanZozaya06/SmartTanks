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
  });

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Completa el nombre y la zona horaria de la casa.');
      return;
    }

    const value = this.form.getRawValue();
    const payload: HomeSetupRequest = {
      name: value.homeName.trim(),
      timezone: value.timezone.trim(),
      displayName: this.displayName(),
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
