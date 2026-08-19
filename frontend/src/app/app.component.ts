import { Component, effect, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';

import { AuthPanelComponent } from './auth/auth-panel.component';
import { ApiService } from './core/api.service';
import { AuthService } from './core/auth.service';
import { AppContext } from './core/models';
import { DashboardComponent } from './dashboard/dashboard.component';
import { HomeSetupComponent } from './onboarding/home-setup.component';

@Component({
  selector: 'app-root',
  imports: [AuthPanelComponent, DashboardComponent, HomeSetupComponent],
  templateUrl: './app.component.html',
  styles: `
    .app-state {
      display: grid;
      min-height: 100vh;
      place-items: center;
      padding: 24px;
      text-align: center;
    }
    .app-state h1 { margin: 0 0 10px; letter-spacing: -0.04em; }
    .app-state p { margin: 0 0 20px; color: #637572; }
    .app-state button {
      padding: 11px 16px;
      border: 0;
      border-radius: 10px;
      color: #fff;
      background: #1f7068;
      font-weight: 800;
      cursor: pointer;
    }
  `,
})
export class AppComponent {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  readonly context = signal<AppContext | null>(null);
  readonly contextStatus = signal<'idle' | 'loading' | 'ready' | 'error'>('idle');
  private contextRequest?: Subscription;
  private loadedUserId?: string;

  constructor() {
    effect(() => {
      const user = this.auth.user();
      if (user === undefined) {
        this.contextStatus.set('loading');
        return;
      }
      if (user === null) {
        this.contextRequest?.unsubscribe();
        this.loadedUserId = undefined;
        this.context.set(null);
        this.contextStatus.set('idle');
        return;
      }
      if (this.loadedUserId !== user.uid) {
        this.loadedUserId = user.uid;
        this.loadContext();
      }
    });
  }

  loadContext(): void {
    this.contextRequest?.unsubscribe();
    this.contextStatus.set('loading');
    this.contextRequest = this.api.context().subscribe({
      next: (context) => {
        this.context.set(context);
        this.contextStatus.set('ready');
      },
      error: () => this.contextStatus.set('error'),
    });
  }

  homeCreated(context: AppContext): void {
    this.context.set(context);
    this.contextStatus.set('ready');
  }

  async logout(): Promise<void> {
    await this.auth.logout();
  }
}
