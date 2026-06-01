import { createApp } from 'vue';
import { createPinia } from 'pinia';
import './assets/theme.css';
import App from './App.vue';

// ── Theme init ──
const saved = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', saved);
globalThis.__theme = saved;
globalThis.__toggleTheme = () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  globalThis.__theme = next;
};

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.mount('#app');
