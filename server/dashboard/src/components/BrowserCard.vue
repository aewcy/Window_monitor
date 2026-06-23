<script setup>
import { ref } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'
import { useScreenshotStore } from '../stores/screenshot'

const agent = useAgentStore()
const ss = useScreenshotStore()
const records = ref([])
const offset = ref(0)
const hasMore = ref(true)
const loading = ref(false)
const BATCH = 20

async function load() {
  if (!agent.selectedAgent) return
  offset.value = 0
  hasMore.value = true
  try {
    loading.value = true
    records.value = await api.getBrowserHistory(agent.selectedAgent, BATCH, 0, agent.selectedMonitor)
    hasMore.value = records.value.length >= BATCH
  } catch {} finally { loading.value = false }
}

async function loadMore() {
  if (!hasMore.value || loading.value) return
  offset.value += BATCH
  try {
    loading.value = true
    const more = await api.getBrowserHistory(agent.selectedAgent, BATCH, offset.value, agent.selectedMonitor)
    records.value.push(...more)
    hasMore.value = more.length >= BATCH
  } catch {} finally { loading.value = false }
}

function onClick(r, idx) {
  if (r.screenshot_id) {
    ss.browseBrowser(records.value, idx)
    ss.liveOpen = true
  }
}

defineExpose({ load })
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--amber)"></span> 浏览器历史</span>
      <span class="card-count" v-if="records.length">{{ records.length }} 条</span>
    </div>
    <div class="card-body">
      <div v-for="(r, idx) in records" :key="r.id"
        class="br-row" :class="{ clickable: r.screenshot_id }"
        @click="onClick(r, idx)">
        <span class="br-icon" :class="(r.browser||'').toLowerCase().includes('edge') ? 'edge' : 'chrome'">
          {{ (r.browser||'').toLowerCase().includes('edge') ? 'E' : 'C' }}
        </span>
        <span class="br-title">{{ r.title || r.url }}</span>
        <span class="br-url">{{ r.url }}</span>
        <span class="br-time">{{ (r.last_visit||'').replace('T',' ').substring(11,16) }}</span>
        <span class="br-count">{{ r.visit_count }}</span>
      </div>
      <div v-if="!records.length && !loading" class="empty">暂无记录</div>
      <div v-if="hasMore && records.length" class="load-more" @click="loadMore">
        {{ loading ? '加载中...' : '加载更多' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-lg); overflow: hidden; display: flex; flex-direction: column; }
.card-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--hairline); flex-shrink: 0; }
.card-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; display: flex; align-items: center; gap: 8px; }
.card-count { font-size: 10px; color: var(--muted); font-family: var(--font-mono); }
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
.load-more { text-align: center; padding: 10px; font-size: 11px; color: var(--accent); cursor: pointer; transition: background .1s; }
.load-more:hover { background: rgba(255,255,255,.04); }
</style>
