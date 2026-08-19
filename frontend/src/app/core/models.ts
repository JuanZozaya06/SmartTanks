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
  name: string;
  shape: 'cylinder';
  heightCm: number;
  diameterCm: number;
  capacityLiters: number;
  lowLevelPercentage: number;
  status: 'active' | 'inactive';
}

export interface AppContext {
  user: UserProfile;
  home: HomeSummary | null;
  tanks: TankConfiguration[];
}

export interface TankSetupRequest {
  name: string;
  heightCm: number;
  diameterCm: number;
  capacityLiters: number;
  lowLevelPercentage: number;
}

export interface HomeSetupRequest {
  name: string;
  timezone: string;
  displayName: string | null;
  tanks: TankSetupRequest[];
}

export interface DeviceChannel {
  channel: string;
  tankId: string;
}

export interface DeviceSummary {
  id: string;
  label: string;
  status: 'active' | 'inactive' | 'unclaimed';
  firmwareVersion: string | null;
  channels: DeviceChannel[];
  lastSeenAt: string | null;
  claimedAt: string | null;
}
