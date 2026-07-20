<script lang="ts">
  import { riskColor } from '$lib/format';
  let { value }: { value: number | null } = $props();
</script>

{#if value === null || value === undefined}
  <span class="missing" title="Risk Index non pubblicato: dati insufficienti o rischio non quantificabile">n/d</span>
{:else}
  <span class="riskbar" title="Indice ordinale 0–100, NON una probabilità">
    <span class="track"><span class="fill" style="width:{value}%; background:{riskColor(value)}"></span></span>
    <span class="val" style="color:{riskColor(value)}">{Math.round(value)}</span>
  </span>
{/if}
