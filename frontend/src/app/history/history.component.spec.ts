import { signal } from '@angular/core';
import { TestBed, fakeAsync, flushMicrotasks, tick } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { ApiService } from '../core/api.service';
import { AppSessionService } from '../core/app-session.service';
import { AuthService } from '../core/auth.service';
import { AppContext, TankHistoryResponse } from '../core/models';
import { RealtimeTankState, TankRealtimeService } from '../core/tank-realtime.service';
import { HistoryComponent } from './history.component';

const tank = { tankId: 'tank-01', name: 'Principal' } as RealtimeTankState;
const response = {
  tank: { id: 'tank-01', name: 'Principal' } as TankHistoryResponse['tank'],
  period: 'day',
  from: '2026-08-19T00:00:00Z',
  to: '2026-08-20T00:00:00Z',
  bucketSeconds: 300,
  sampleCount: 0,
  skippedCount: 0,
  reconstructedTimestampCount: 0,
  points: [],
} as TankHistoryResponse;

class ApiServiceStub {
  calls = 0;

  tankHistory() {
    this.calls += 1;
    return of(response);
  }
}

class AuthServiceStub {
  async logout(): Promise<void> {}
}

class AppSessionServiceStub {
  readonly context = signal({
    user: { id: 'user-01', displayName: null, email: null },
    home: { id: 'home-01', name: 'Casa', timezone: 'America/Caracas', role: 'owner' },
    tanks: [],
  } as AppContext);
}

class TankRealtimeServiceStub {
  next?: (tanks: RealtimeTankState[]) => void;

  listen(
    _homeId: string,
    next: (tanks: RealtimeTankState[]) => void,
  ): () => void {
    this.next = next;
    return () => {};
  }
}

describe('HistoryComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HistoryComponent],
      providers: [
        provideRouter([]),
        { provide: ApiService, useClass: ApiServiceStub },
        { provide: AuthService, useClass: AuthServiceStub },
        { provide: AppSessionService, useClass: AppSessionServiceStub },
        { provide: TankRealtimeService, useClass: TankRealtimeServiceStub },
      ],
    }).compileComponents();
  });

  it('reloads the selected history whenever the realtime tank state changes', fakeAsync(() => {
    const fixture = TestBed.createComponent(HistoryComponent);
    const realtime = TestBed.inject(TankRealtimeService) as unknown as TankRealtimeServiceStub;
    const api = TestBed.inject(ApiService) as unknown as ApiServiceStub;
    fixture.detectChanges();

    realtime.next?.([tank]);
    tick(300);
    flushMicrotasks();
    expect(api.calls).toBe(1);

    realtime.next?.([tank]);
    tick(300);
    flushMicrotasks();
    expect(api.calls).toBe(2);
  }));
});
