import { Component, effect, inject, signal } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';
import { Subscription } from 'rxjs';

import { AuthPanelComponent } from './auth/auth-panel.component';
import { ApiService } from './core/api.service';
import { AppSessionService } from './core/app-session.service';
import { AuthService } from './core/auth.service';
import { AppContext } from './core/models';
import { HomeSetupComponent } from './onboarding/home-setup.component';

@Component({
  selector: 'app-root',
  imports: [AuthPanelComponent, HomeSetupComponent, RouterOutlet],
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
    .app-state .brand-logo { margin-inline: auto; }
    .app-state p { margin: 0 0 20px; color: var(--color-muted); }
    .app-state button {
      padding: 11px 16px;
      border: 0;
      border-radius: 10px;
      color: #fff;
      background: linear-gradient(135deg, var(--color-primary), var(--color-primary-deep));
      box-shadow: 0 10px 26px rgb(0 100 230 / 22%);
      font-weight: 800;
      cursor: pointer;
    }
  `,
})
export class AppComponent {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly session = inject(AppSessionService);
  readonly auth = inject(AuthService);
  readonly context = this.session.context;
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
        this.session.context.set(null);
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
        this.session.context.set(context);
        this.contextStatus.set('ready');
      },
      error: () => this.contextStatus.set('error'),
    });
  }

  homeCreated(context: AppContext): void {
    this.session.context.set(context);
    this.contextStatus.set('ready');
    void this.router.navigateByUrl('/');
  }

  async logout(): Promise<void> {
    await this.auth.logout();
    void this.router.navigateByUrl('/');
  }
}
