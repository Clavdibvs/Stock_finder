<script lang="ts">
  let { grade }: { grade: string | null } = $props();
  const titles: Record<string, string> = {
    A: 'Confidence A: dati critici completi, fonte primaria o più origini indipendenti',
    B: 'Confidence B: dati di mercato completi, intelligence in parte secondaria',
    C: 'Confidence C: mancano float, economics, origine o dati rilevanti',
    D: 'Confidence D: dati incoerenti, ritardati o claim non ricostruibile'
  };
</script>

{#if grade}
  <span class="conf g{grade}" title={titles[grade] ?? ''}>{grade}</span>
{:else}
  <span class="missing">n/d</span>
{/if}
