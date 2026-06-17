<script setup>
import { ref } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'
import { useScreenshotStore } from '../stores/screenshot'

const agent = useAgentStore()
const ss = useScreenshotStore()
const records = ref([])

async function load() {
  if (!agent.selectedAgent) return
  try { records.value = await api.getBrowserHistory(agent.selectedAgent, 20) } catch {}
}

function onClick(r) {
  if (r.screenshot_id) {
    ss.showById(r.screenshot_id)
  }
}

defineExpose({ load })
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--amber)"></span> 浏览器历史</span>
    </div>
    <div class="card-body">
      <div v-for="r in records" :key="r.id"
        class="br-row" :class="{ clickable: r.screenshot_id }"
        @click="onClick(r)">
        <span class="br-icon" :class="(r.browser||'').toLowerCase().includes('edge') ? 'edge' : 'chrome'">
          {{ (r.browser||'').toLowerCase().includes('edge') ? 'E' : 'C' }}
        </span>
        <span class="br-title">{{ r.title || r.url }}</span>
        <span class="br-url">{{ r.url }}</span>
        <span class="br-time">{{ (r.last_visit||'').replace('T',' ').substring(11,16) }}</span>
        <span class="br-count">{{ r.visit_count }}</span>
      </div>
      <div v-if="!records.length" class="empty">暂无记录</div>
    </div>
  </div>
</template>

<style scoped>
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-lg); overflow: hidden; display: flex; flex-direction: column; }
.card-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--hairline); flex-shrink: 0; }
.card-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.card-body { flex: 1; overflow-y: auto; min-height: 0; }
.br-row { display: flex; align-items: center; gap: 10px; padding: 5px 16px; border-bottom: 1px solid rgba(255,255,255,.02); font-size: 12px; transition: background .1s; }
.br-row:hover { background: rgba(255,255,255,.03); }
.br-row.clickable { cursor: pointer; }
.br-row.clickable:hover { background: rgba(96,165,250,.08); }
.br-icon { width: 16px; height: 16px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 700; flex-shrink: 0; }
.br-icon.chrome { background: rgba(96,165,250,.15); color: var(--blue); }
.br-icon.edge { background: rgba(96,165,250,.15); color: var(--blue); }
.br-title { color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-url { font-family: var(--font-mono); font-size: 10px; color: var(--muted); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-time { font-family: var(--font-mono); font-size: 10px; color: var(--muted); min-width: 44px; text-align: right; }
.br-count { font-family: var(--font-mono); font-size: 10px; color: var(--amber); min-width: 24px; text-align: right; }
.empty { color: var(--muted); padding: 16px; text-align: center; font-size: 11px; }
</style>
