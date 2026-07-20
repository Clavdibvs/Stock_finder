<script lang="ts">
  /** Evoluzione del Risk Index nel tempo (piccolo multiplo, un solo asse). */
  import { day } from '$lib/format';
  type Point = { date: string; risk_index: number | null; state: string };
  let { points }: { points: Point[] } = $props();

  const W = 320, H = 72, PAD = 6;
  let valid = $derived(points.filter((p) => p.risk_index !== null));
  let x = $derived((i: number) => PAD + (i / Math.max(1, valid.length - 1)) * (W - PAD * 2));
  let y = $derived((v: number) => PAD + (1 - v / 100) * (H - PAD * 2));
  let path = $derived(
    valid.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.risk_index as number).toFixed(1)}`).join(' ')
  );
</script>

{#if valid.length === 0}
  <span class="missing">nessuno storico numerico</span>
{:else}
  <svg viewBox="0 0 {W} {H}" style="width:100%; max-width:{W}px; height:auto" role="img"
       aria-label="Storico del Risk Index">
    <line x1={PAD} x2={W - PAD} y1={y(70)} y2={y(70)} stroke="var(--state-elevated)" stroke-width="1" stroke-dasharray="2 4" opacity="0.5" />
    <line x1={PAD} x2={W - PAD} y1={y(55)} y2={y(55)} stroke="var(--accent)" stroke-width="1" stroke-dasharray="2 4" opacity="0.4" />
    <path d={path} fill="none" stroke="var(--chart-line)" stroke-width="2" stroke-linejoin="round" />
    {#each valid as p, i}
      <circle cx={x(i)} cy={y(p.risk_index as number)} r="4" fill="var(--chart-line)"
              stroke="var(--bg-raised)" stroke-width="2">
        <title>{day(p.date)}: {Math.round(p.risk_index as number)} — {p.state}</title>
      </circle>
    {/each}
    <text x={W - PAD} y={y(70) - 3} fill="var(--state-elevated)" font-size="9" text-anchor="end" opacity="0.8">70</text>
    <text x={W - PAD} y={y(55) - 3} fill="var(--accent)" font-size="9" text-anchor="end" opacity="0.8">55</text>
  </svg>
{/if}
