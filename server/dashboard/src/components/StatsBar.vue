<script setup>
import { computed, ref, onMounted } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'

const agent = useAgentStore()
const stats = ref({})
const storage = ref({})

function formatBytes(bytes) {
  const n = Number(bytes || 0)
  if (n >= 1024 * 1024 * 1024) return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

const currentStorage = computed(() => {
  const rows = storage.value.agents || []
  if (!agent.selectedAgent) return storage.value.total_size_bytes || 0
  return rows.find(row => row.agent_name === agent.selectedAgent)?.total_size || 0
})

async function load() {
  try {
    const [statsData, storageData] = await Promise.all([
      api.getStats(agent.selectedAgent),
      api.getStorageStats(),
    ])
    stats.value = statsData
    storage.value = storageData
  } catch {}
}

defineExpose({ load })
onMounted(load)
</script>

<template>
  <div class="stats-bar">
    <div class="stat-pill"><span class="dot-live"></span> 在线 <span class="val">{{ stats.online_agents ?? 0 }}</span></div>
    <div class="stat-pill">截图 <span class="val">{{ stats.total_screenshots ?? 0 }}</span></div>
    <div class="stat-pill">占用 <span class="val">{{ formatBytes(currentStorage) }}</span></div>
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
