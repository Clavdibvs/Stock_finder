<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api, setCsrf, ApiError } from '$lib/api';

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let locked = $state(false);
  let busy = $state(false);

  async function submit(ev: SubmitEvent) {
    ev.preventDefault();
    busy = true;
    error = '';
    locked = false;
    try {
      const res = await api.post<{ authenticated: boolean; csrf_token: string | null }>(
        '/api/auth/login', { username, password }
      );
      if (res.csrf_token) setCsrf(res.csrf_token);
      const next = page.url.searchParams.get('next') ?? '/';
      goto(next.startsWith('/') ? next : '/');
    } catch (e) {
      // messaggi volutamente non informativi
      if (e instanceof ApiError && e.status === 429) {
        locked = true;
        error = 'Accesso temporaneamente bloccato. Riprovare più tardi.';
      } else {
        error = 'Credenziali non valide.';
      }
    } finally {
      busy = false;
    }
  }
</script>

<div class="login-wrap">
  <div class="login-box">
    <h1>DRAWDOWN RADAR</h1>
    <div class="sub">Accesso privato — nessuna registrazione</div>
    <form onsubmit={submit}>
      <input type="text" placeholder="Utente" bind:value={username}
             autocomplete="username" required maxlength="64" />
      <input type="password" placeholder="Password" bind:value={password}
             autocomplete="current-password" required maxlength="256" />
      <div class="error-line" class:mono={locked}>{error}</div>
      <button class="primary" type="submit" disabled={busy || locked}>
        {busy ? 'Verifica…' : 'Entra'}
      </button>
    </form>
  </div>
</div>
