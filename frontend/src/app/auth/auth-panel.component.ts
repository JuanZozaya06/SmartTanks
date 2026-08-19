import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AuthService, authErrorMessage } from '../core/auth.service';

@Component({
  selector: 'app-auth-panel',
  imports: [ReactiveFormsModule],
  templateUrl: './auth-panel.component.html',
  styleUrl: './auth-panel.component.scss',
})
export class AuthPanelComponent {
  private readonly auth = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);

  readonly mode = signal<'login' | 'register'>('login');
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.formBuilder.nonNullable.group({
    displayName: ['', [Validators.maxLength(100)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(6)]],
  });

  setMode(mode: 'login' | 'register'): void {
    this.mode.set(mode);
    this.error.set(null);
  }

  async submit(): Promise<void> {
    const displayName = this.form.controls.displayName.value.trim();
    if (this.form.invalid || (this.mode() === 'register' && !displayName)) {
      this.form.markAllAsTouched();
      this.error.set('Completa correctamente todos los campos.');
      return;
    }

    this.submitting.set(true);
    this.error.set(null);
    try {
      const { email, password } = this.form.getRawValue();
      if (this.mode() === 'register') {
        await this.auth.register(displayName, email, password);
      } else {
        await this.auth.login(email, password);
      }
    } catch (cause) {
      this.error.set(authErrorMessage(cause));
    } finally {
      this.submitting.set(false);
    }
  }
}
