import { Injectable, signal } from '@angular/core';

import { AppContext } from './models';

@Injectable({ providedIn: 'root' })
export class AppSessionService {
  readonly context = signal<AppContext | null>(null);
}
