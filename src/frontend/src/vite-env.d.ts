/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_TOKEN?: string;
  readonly VITE_WORKER_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
