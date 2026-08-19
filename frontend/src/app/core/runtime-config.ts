import { FirebaseOptions } from 'firebase/app';

export interface RuntimeConfig {
  apiBaseUrl: string;
  firebase: FirebaseOptions;
  useEmulators?: boolean;
}

declare global {
  interface Window {
    __SMART_TANKS_CONFIG__?: RuntimeConfig;
  }
}

function loadRuntimeConfig(): RuntimeConfig {
  const config = window.__SMART_TANKS_CONFIG__;
  const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

  if (config && (!isLocal || !config.useEmulators)) {
    return config;
  }

  if (isLocal) {
    return {
      apiBaseUrl: 'http://127.0.0.1:5001/smarttanks-830ba/us-east1/api',
      useEmulators: true,
      firebase:
        config?.firebase ??
        {
          apiKey: 'demo-key',
          authDomain: 'smarttanks-830ba.firebaseapp.com',
          projectId: 'smarttanks-830ba',
          appId: 'demo-app-id',
        },
    };
  }

  throw new Error('Falta la configuración de SmartTanks en public/config.js.');
}

export const runtimeConfig = loadRuntimeConfig();
