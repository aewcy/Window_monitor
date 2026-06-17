<script setup>
import { ref, onMounted } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'

const agent = useAgentStore()
const stats = ref({})

async function load() {
  try { stats.value = await api.getStats(agent.selectedAgent) } catch {}
}

defineExpose({ load })
onMounted(load)
</script>

<template>
  <div class="stats-bar">
    <div class="stat-pill"><span class="dot-live"></span> 在线 <span class="val">{{ stats.online_agents ?? 0 }}</span></div>
    <div class="stat-pill">截图 <span class="val">{{ stats.total_screenshots ?? 0 }}</span></div>
    <div class="stat-pill">事件 <span class="val">{{ stats.today_app_events ?? 0 }}</span></div>
    <div class="stat-pill">网址 <span class="val">{{ stats.total_browser_records ?? 0 }}</span></div>
  </div>
</template>

<style scoped>
.stats-bar {
  position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 2px; background: rgba(255,255,255,0.06);
  border: 1px solid var(--hairline); border-radius: var(--radius-xl);
  padding: 6px 8px; backdrop-filter: blur(20px); box-shadow: var(--shadow-lift); z-index: 100;
}
.stat-pill {
  display: flex; align-items: center; gap: 6px; padding: 4px 14px;
  border-radius: 20px; font-size: 11px; font-weight: 500; color: var(--text-secondary);
}
.stat-pill .val { font-family: var(--font-mono); font-weight: 600; color: var(--text); }
.dot-live { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
</style>
