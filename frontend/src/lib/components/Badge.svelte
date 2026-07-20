<script lang="ts">
  import { stateClass, stateShort } from '$lib/format';
  let { state, full = false }: { state: string | null; full?: boolean } = $props();
</script>

<span class="badge {stateClass(state)}" title={state ?? ''}>
  {full ? state : stateShort(state)}
</span>
