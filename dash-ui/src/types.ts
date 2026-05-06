export type Language = 'en' | 'hu';

export interface DashUser {
  username: string;
  is_admin: boolean;
  can_restart: boolean;
  can_view_logs: boolean;
}

export interface AudioStatus {
  configured_backend: string;
  effective_backend: string;
  lavalink_requested: boolean;
  lavalink_connected: boolean;
  lavalink_uri: string;
}

export interface Stats {
  sampled_at?: number;
  ping: number;
  guilds: number;
  users: number;
  voice_clients: number;
  ram_usage_mb: number;
  cpu_usage: number;
  uptime: string;
  audio?: AudioStatus;
}

export interface HistoryPoint {
  t: number;
  cpu: number;
  ram: number;
  ping: number;
}

export interface DashboardUser {
  id: number;
  username: string;
  is_admin: boolean;
  can_restart: boolean;
  can_view_logs: boolean;
  password_display?: string;
  created_at?: string;
}
