<script setup>
import { ref } from 'vue'
import * as api from '../api'

const logs = ref([])

async function load() {
  try { logs.value = await api.getLogs(20) } catch {}
}

defineExpose({ load })

const levelClass = (l) => ({ INFO: 'info', WARNING: 'warn', ERROR: 'error' }[l] || 'info')
const catLabel = { network:'网络', storage:'存储', capture:'采集', system:'系统', security:'安全', server:'服务端' }
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--accent)"></span> 系统日志</span>
    </div>
    <div class="card-body">
      <div v-for="e in logs" :key="e.id" class="log-row">
        <span class="log-time">{{ (e.timestamp||'').replace('T',' ').substring(11,16) }}</span>
        <span class="log-level" :class="levelClass(e.level)">{{ e.level }}</span>
        <span class="log-cat">{{ catLabel[e.category] || e.category }}</span>
        <span class="log-msg">{{ e.message }}</span>
      </div>
      <div v-if="!logs.length" class="empty">暂无日志</div>
    </div>
  </div>
</template>

<style scoped>
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-lg); overflow: hidden; display: flex; flex-direction: column; }
.card-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--hairline); flex-shrink: 0; }
.card-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.card-body { flex: 1; overflow-y: auto; min-height: 0; }
.log-row { display: flex; align-items: flex-start; gap: 8px; padding: 4px 16px; border-bottom: 1px solid rgba(255,255,255,.02); font-size: 12px; line-height: 1.5; }
.log-row:hover { background: rgba(255,255,255,.03); }
.log-time { font-family: var(--font-mono); font-size: 10px; color: var(--muted); min-width: 44px; flex-shrink: 0; }
.log-level { font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px; min-width: 36px; text-align: center; flex-shrink: 0; }
.log-level.info { background: rgba(251,191,36,.1); color: var(--amber); }
.log-level.warn { background: rgba(251,191,36,.18); color: #FCD34D; }
.log-level.error { background: rgba(242,54,69,.12); color: var(--red); }
.log-cat { font-size: 9px; padding: 1px 6px; border-radius: 4px; background: var(--surface); color: var(--muted); flex-shrink: 0; }
.log-msg { color: var(--text-secondary); flex: 1; word-break: break-all; min-width: 0; }
.empty { color: var(--muted); padding: 16px; text-align: center; font-size: 11px; }
</style>
