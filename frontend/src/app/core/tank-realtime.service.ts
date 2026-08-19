import { Injectable, inject } from '@angular/core';
import { DocumentData, Unsubscribe, doc, onSnapshot } from 'firebase/firestore';

import { FirebaseService } from './firebase.service';

export interface RealtimeTankState {
  tankId: string;
  percentage: number;
  liters: number;
  waterHeightCm: number;
  updatedAt: Date;
}

function numericValue(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function dateValue(value: unknown): Date {
  if (value instanceof Date) {
    return value;
  }

  if (value && typeof value === 'object' && 'toDate' in value) {
    const toDate = (value as { toDate?: unknown }).toDate;
    if (typeof toDate === 'function') {
      return toDate.call(value) as Date;
    }
  }

  if (typeof value === 'string') {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }

  return new Date(0);
}

export function mapTankState(tankId: string, data: DocumentData): RealtimeTankState | null {
  const latestReading = data['latestReading'];
  if (!latestReading || typeof latestReading !== 'object') {
    return null;
  }

  return {
    tankId,
    percentage: numericValue(latestReading['percentage']),
    liters: numericValue(latestReading['liters']),
    waterHeightCm: numericValue(latestReading['waterHeightCm']),
    updatedAt: dateValue(latestReading['receivedAt'] ?? data['lastCommunicationAt']),
  };
}

@Injectable({ providedIn: 'root' })
export class TankRealtimeService {
  private readonly firebase = inject(FirebaseService);

  listen(
    homeId: string,
    tankId: string,
    next: (state: RealtimeTankState | null) => void,
    error: (cause: Error) => void,
  ): Unsubscribe {
    const tankReference = doc(this.firebase.firestore, 'homes', homeId, 'tanks', tankId);

    return onSnapshot(
      tankReference,
      (snapshot) => next(snapshot.exists() ? mapTankState(tankId, snapshot.data()) : null),
      error,
    );
  }
}
