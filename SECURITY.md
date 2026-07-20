# Sicurezza

## Modello di minaccia

Istanza personale mono-utente su VPS. Minacce considerate: accesso non
autorizzato dall'esterno, furto di API key, prompt injection dai documenti
ingeriti, SSRF attraverso l'ingestion, manomissione dei dati storici, perdita
dei dati. Fuori scopo: attaccanti con accesso fisico al VPS, compromissione
della supply chain dei container di base.

## Accesso

- **Un solo account amministratore**, creato dalla configurazione al bootstrap.
  Nessuna pagina o endpoint di registrazione (verificato da test).
- Password con **Argon2id**; nel DB delle sessioni si salva solo l'hash SHA-256
  del token (un dump del DB non consente il riuso delle sessioni).
- Cookie `HttpOnly` + `Secure` + `SameSite=Strict`; TTL 12 ore; logout revoca.
- **CSRF**: double-submit token obbligatorio su ogni metodo mutante (oltre a
  SameSite=Strict).
- **Rate limiting sul login** (10 tentativi/min per IP) + **lockout account**
  (5 tentativi falliti → blocco 15 min). Messaggi d'errore non informativi:
  non rivelano se l'utente esiste o se l'account è bloccato.
- **`DDR_AUTH_DISABLED=true`** disattiva il login applicativo SOLO quando
  l'istanza è raggiungibile esclusivamente via Tailscale/WireGuard o access
  proxy. Mai su interfaccia pubblica.
- Nessuna documentazione API esposta (`/docs`, `/redoc`, `/openapi.json` → 404).

## Rete e deploy

- Solo Caddy espone porte; API e PostgreSQL vivono sulla rete Docker interna.
- TLS automatico (Let's Encrypt) con dominio reale; HSTS; security header
  (nosniff, DENY, no-referrer, CSP `default-src 'self'` — la SPA non contatta
  alcun host esterno, font inclusi).
- Container API con utente non-root; least privilege sul DB (un solo ruolo
  applicativo, nessun superuser usato dall'app).
- Aggiornamenti: `docker compose pull/build` periodico; dependency scanning
  consigliato in CI (`pip-audit`, `npm audit`) prima di ogni aggiornamento.

## Ingestion (SSRF e contenuti)

Fetcher unico (`app/core/http.py`):
- allowlist di domini da configurazione, verificata anche a ogni redirect;
- solo HTTPS; risoluzione DNS verificata contro IP privati/loopback/link-local;
- timeout (20 s) e limite dimensione (5 MB); content-type validato;
- rispetto di robots.txt/ToS a livello di policy: si integrano solo API o feed
  ufficiali (vedi SOURCE_REGISTRY.md).

## Segreti e log

- Nessun segreto nel repository: `.env` è gitignored, `.env.example` non
  contiene valori reali; il bootstrap genera segreti casuali con permessi 600.
- Le API key non vengono mai restituite dalle API né mostrate in UI (solo
  presente/assente).
- Logging con filtro di **redazione automatica** (api key, token, bearer,
  password) su tutti gli handler.

## Prompt injection (AI opzionale)

- Il testo esterno è **sempre un dato**: viaggia in un campo JSON separato,
  mai concatenato alle istruzioni di sistema.
- Il prompt di sistema ordina di ignorare istruzioni contenute nei documenti;
  nessun tool/funzione è esposto al modello.
- Output vincolato a JSON Schema con tassonomia chiusa e
  `additionalProperties: false`: campi extra (es. "risk_score") = rifiuto.
- Evidence span obbligatorio; output non conformi scartati e registrati
  (`ai_invocations.status`, `data_quality_issues`).
- L'AI non può: modificare dati raw, inventare numeri, calcolare score,
  dichiarare shortabilità, lanciare job, accedere a segreti.
- Tetto di spesa mensile (`DDR_AI_MONTHLY_BUDGET_EUR`): superato, nessuna chiamata.

## Audit e integrità

- `audit_logs` append-only con **catena di hash** (ogni riga incorpora l'hash
  della precedente); `verify_chain()` rileva manomissioni. Nessun endpoint di
  modifica o cancellazione.
- Azioni tracciate: login, override manuali, run manuali di job, modifiche
  watchlist, export, seed.
- Ogni correzione manuale richiede un motivo e produce sia `manual_overrides`
  sia una riga di audit.

## Backup e restore

- `scripts/backup.sh`: `pg_dump` + snapshot Parquet → **Restic** (cifrato,
  deduplicato) verso repository esterno (SFTP/S3-compatibile); retention
  14 giorni / 8 settimane / 12 mesi.
- `scripts/restore.sh`: ripristino in database parallelo + swap atomico con
  conferma esplicita; il vecchio DB resta disponibile per rollback.
- **Provare il restore periodicamente**: un backup mai ripristinato non è un
  backup. Suggerito: test trimestrale documentato.

## Dati personali e copyright

- Dei contenuti di terzi si conservano metadati, hash, estratti brevi e
  classificazioni; mai copie integrali automatiche di articoli protetti.
- Contenuti da community: retention breve (`DDR_RETENTION_SOCIAL_DAYS`,
  default 30 giorni) e cancellazione su richiesta; niente profili completi;
  hash degli username quando l'identità non serve.
- Registro delle fonti con stato di licenza in `document_sources` (visibile
  in UI).
