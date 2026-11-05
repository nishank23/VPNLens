import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const proxy = {
  '/v1': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
  '/docs': 'http://127.0.0.1:8000',
  '/openapi.json': 'http://127.0.0.1:8000',
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  build: { target: 'es2022' },
});
