import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { from, map, switchMap, throwError } from 'rxjs';

import { FirebaseService } from './firebase.service';
import {
  AppContext,
  DeviceSummary,
  HomeSetupRequest,
  TankConfiguration,
  TankUpdateRequest,
} from './models';
import { runtimeConfig } from './runtime-config';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly firebase = inject(FirebaseService);
  private readonly baseUrl = runtimeConfig.apiBaseUrl.replace(/\/$/, '');

  health() {
    return this.http.get<{ status: string; service: string }>(`${this.baseUrl}/v1/health`);
  }

  context() {
    return this.authorizationHeaders().pipe(
      switchMap((headers) =>
        this.http.get<AppContext>(`${this.baseUrl}/v1/me/context`, { headers }),
      ),
    );
  }

  createHome(payload: HomeSetupRequest) {
    return this.authorizationHeaders().pipe(
      switchMap((headers) =>
        this.http.post<AppContext>(`${this.baseUrl}/v1/homes`, payload, { headers }),
      ),
    );
  }

  devices(homeId: string) {
    return this.authorizationHeaders().pipe(
      switchMap((headers) =>
        this.http.get<{ devices: DeviceSummary[] }>(
          `${this.baseUrl}/v1/homes/${encodeURIComponent(homeId)}/devices`,
          { headers },
        ),
      ),
    );
  }

  claimDevice(homeId: string, deviceId: string, setupPin: string, label: string) {
    return this.authorizationHeaders().pipe(
      switchMap((headers) =>
        this.http.post<{ device: DeviceSummary }>(
          `${this.baseUrl}/v1/homes/${encodeURIComponent(homeId)}/devices/claim`,
          { deviceId, setupPin, label },
          { headers },
        ),
      ),
    );
  }

  updateTank(homeId: string, tankId: string, payload: TankUpdateRequest) {
    return this.authorizationHeaders().pipe(
      switchMap((headers) =>
        this.http.patch<{ tank: TankConfiguration }>(
          `${this.baseUrl}/v1/homes/${encodeURIComponent(homeId)}/tanks/${encodeURIComponent(tankId)}`,
          payload,
          { headers },
        ),
      ),
    );
  }

  private authorizationHeaders() {
    const user = this.firebase.auth.currentUser;
    if (!user) {
      return throwError(() => new Error('No existe una sesión autenticada.'));
    }
    return from(user.getIdToken()).pipe(
      map((token) => new HttpHeaders({ Authorization: `Bearer ${token}` })),
    );
  }
}
