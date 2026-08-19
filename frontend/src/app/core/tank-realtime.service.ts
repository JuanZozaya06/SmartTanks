import { Injectable, inject } from '@angular/core';
import { DocumentData, Unsubscribe, collection, onSnapshot } from 'firebase/firestore';

import { FirebaseService } from './firebase.service';

export interface RealtimeTankState {
  tankId: string;
  deviceId: string;
  sensorId: string;
  name: string;
  configurationStatus: 'pending' | 'configured';
  status: 'active' | 'inactive';
  percentage: number | null;
  liters: number | null;
  waterHeightCm: number | null;
  pressureKpa: number | null;
  capacityLiters: number | null;
  lowLevelPercentage: number;
  updatedAt: Date;
}

function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
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
  const deviceId = data['deviceId'];
  const sensorId = data['sensorId'];
  const latestReading = data['latestReading'];
  if (
    typeof deviceId !== 'string' ||
    typeof sensorId !== 'string' ||
    !latestReading ||
    typeof latestReading !== 'object'
  ) {
    return null;
  }

  return {
    tankId,
    deviceId,
    sensorId,
    name:
      typeof data['name'] === 'string' && data['name'].trim()
        ? data['name']
        : `Tanque ${sensorId}`,
    configurationStatus: data['configurationStatus'] === 'configured' ? 'configured' : 'pending',
    status: data['status'] === 'inactive' ? 'inactive' : 'active',
    percentage: numericValue(latestReading['percentage']),
    liters: numericValue(latestReading['liters']),
    waterHeightCm: numericValue(latestReading['waterHeightCm']),
    pressureKpa: numericValue(latestReading['pressureKpa']),
    capacityLiters: numericValue(data['capacityLiters']),
    lowLevelPercentage: numericValue(data['lowLevelPercentage']) ?? 25,
    updatedAt: dateValue(latestReading['receivedAt'] ?? data['lastCommunicationAt']),
  };
}

@Injectable({ providedIn: 'root' })
export class TankRealtimeService {
  private readonly firebase = inject(FirebaseService);

  listen(
    homeId: string,
    next: (states: RealtimeTankState[]) => void,
    error: (cause: Error) => void,
  ): Unsubscribe {
    const tanksReference = collection(this.firebase.firestore, 'homes', homeId, 'tanks');

    return onSnapshot(
      tanksReference,
      (snapshot) => {
        const states = snapshot.docs
          .map((document) => mapTankState(document.id, document.data()))
          .filter((state): state is RealtimeTankState => state !== null)
          .sort((left, right) => left.tankId.localeCompare(right.tankId));
        next(states);
      },
      error,
    );
  }
}
