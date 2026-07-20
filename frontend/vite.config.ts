import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      // sviluppo: il backend FastAPI gira su :8000
      '/api': { target: 'http://localhost:8000', changeOrigin: false }
    }
  }
});
