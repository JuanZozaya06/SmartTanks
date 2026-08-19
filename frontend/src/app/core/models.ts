export interface UserProfile {
  id: string;
  displayName: string | null;
  email: string | null;
}

export interface HomeSummary {
  id: string;
  name: string;
  timezone: string;
  role: 'owner' | 'admin' | 'viewer';
  createdAt?: string;
}

export interface TankConfiguration {
  id: string;
  deviceId: string;
  sensorId: string;
  name: string;
  shape: 'cylinder' | null;
  heightCm: number | null;
  diameterCm: number | null;
  fullPressureKpa: number | null;
  capacityLiters: number | null;
  lowLevelPercentage: number;
  configurationStatus: 'pending' | 'configured';
  status: 'active' | 'inactive';
}

export interface TankUpdateRequest {
  name?: string;
  heightCm?: number;
  diameterCm?: number;
  fullPressureKpa?: number;
}

export interface AppContext {
  user: UserProfile;
  home: HomeSummary | null;
  tanks: TankConfiguration[];
}

export interface HomeSetupRequest {
  name: string;
  timezone: string;
  displayName: string | null;
}

export interface DeviceSummary {
  id: string;
  label: string;
  status: 'active' | 'inactive' | 'unclaimed';
  firmwareVersion: string | null;
  lastSeenAt: string | null;
  claimedAt: string | null;
}

export type HistoryPeriod = 'day' | 'week' | 'month';

export interface TankHistoryPoint {
  observedAt: string;
  firstObservedAt: string;
  lastObservedAt: string;
  sampleCount: number;
  timestampQuality: 'verified' | 'estimated' | 'pending';
  pressureKpa: number | null;
  minPressureKpa: number | null;
  maxPressureKpa: number | null;
  firstPressureKpa: number | null;
  lastPressureKpa: number | null;
  percentage: number | null;
  minPercentage: number | null;
  maxPercentage: number | null;
  firstPercentage: number | null;
  lastPercentage: number | null;
  liters: number | null;
  minLiters: number | null;
  maxLiters: number | null;
  firstLiters: number | null;
  lastLiters: number | null;
}

export interface TankHistoryResponse {
  tank: TankConfiguration;
  period: HistoryPeriod | 'custom';
  from: string;
  to: string;
  bucketSeconds: number;
  sampleCount: number;
  skippedCount: number;
  points: TankHistoryPoint[];
}
