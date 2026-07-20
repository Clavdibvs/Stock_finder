<script lang="ts">
  import '@fontsource-variable/archivo';
  import '@fontsource/jetbrains-mono/400.css';
  import '@fontsource/jetbrains-mono/600.css';
  import '../app.css';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { api, setCsrf } from '$lib/api';

  let { children } = $props();

  let mode: string = $state('');
  let authKnown = $state(false);

  const navItems = [
    { href: '/', icon: '◫', label: 'Dashboard' },
    { href: '/watchlist', icon: '☆', label: 'Watchlist' },
    { href: '/fonti', icon: '¶', label: 'Fonti e claim' },
    { href: '/qualita', icon: '✓', label: 'Data quality' },
    { href: '/impostazioni', icon: '⚙', label: 'Impostazioni' }
  ];

  $effect(() => {
    api.get<{ authenticated: boolean; csrf_token?: string; mode?: string }>('/api/auth/me')
      .then((me) => {
        mode = me.mode ?? '';
        if (me.csrf_token) setCsrf(me.csrf_token);
        if (!me.authenticated && page.url.pathname !== '/login') {
          goto('/login');
        }
        authKnown = true;
      })
      .catch(() => { authKnown = true; });
  });

  async function logout() {
    try { await api.post('/api/auth/logout'); } catch { /* già scaduta */ }
    setCsrf(null);
    goto('/login');
  }

  let isLogin = $derived(page.url.pathname === '/login');
</script>

{#if isLogin}
  {@render children()}
{:else}
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="name">DRAWDOWN RADAR</div>
        <div class="sub">early warning · privato</div>
      </div>
      <nav class="nav" style="flex:1">
        {#each navItems as item}
          <a href={item.href} class:active={page.url.pathname === item.href ||
            (item.href !== '/' && page.url.pathname.startsWith(item.href))}>
            <span class="icon">{item.icon}</span>{item.label}
          </a>
        {/each}
      </nav>
      <div style="padding: 10px 18px; font-size:11px; color: var(--ink-3)">
        {#if mode === 'demo'}<div style="color: var(--accent); font-weight:600">MODALITÀ DEMO</div>{/if}
        <button onclick={logout} style="margin-top:8px; width:100%; font-size:12px">Esci</button>
      </div>
    </aside>
    <main class="main">
      {#if mode === 'demo'}
        <div class="demo-banner">
          <strong>DEMO</strong>
          <span>Dati fittizi o ricostruzioni storiche etichettate. Nulla è aggiornato in tempo reale.</span>
        </div>
      {/if}
      {@render children()}
      <footer class="disclaimer">
        Strumento personale di ricerca — non è consulenza finanziaria, non promette rendimenti e non
        prevede crolli con certezza. Il Risk Index è un indice ordinale, non una probabilità.
        Un rischio elevato di drawdown non implica che il titolo sia shortabile: eventi binari e squeeze
        possono rendere estremamente pericolosa qualsiasi operazione. Nessuna funzione esegue ordini.
      </footer>
    </main>
  </div>
{/if}
