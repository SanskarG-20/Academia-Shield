import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
            configure: (proxy) => {
              proxy.on('error', (err, _req, res) => {
                if (res && 'writeHead' in res && !(res as any).headersSent) {
                  (res as any).writeHead(503, { 'Content-Type': 'application/json' });
                  (res as any).end(JSON.stringify({ detail: 'Backend server is reloading. Please retry in a moment.' }));
                }
              });
            },
          },
          '/socket.io': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
            ws: true,
            configure: (proxy) => {
              proxy.on('error', () => {
                // Ignore transient WebSocket proxy disconnect errors
              });
            },
          },
        },
      },
      plugins: [react()],
      define: {
        'import.meta.env.VITE_API_URL': JSON.stringify(env.VITE_API_URL),
        'import.meta.env.VITE_GEMINI_API_KEY': JSON.stringify(env.VITE_GEMINI_API_KEY),
      },
      resolve: {
        alias: {
          '@': resolve(__dirname, './src'),
        },
      },
    };
});
