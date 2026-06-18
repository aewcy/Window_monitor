<script setup>
import { ref } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'
import { useScreenshotStore } from '../stores/screenshot'

const agent = useAgentStore()
const ss = useScreenshotStore()
const events = ref([])
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
    events.value = await api.getAppEvents(agent.selectedAgent, BATCH, 0)
    hasMore.value = events.value.length >= BATCH
  } catch {} finally { loading.value = false }
}

async function loadMore() {
  if (!hasMore.value || loading.value) return
  offset.value += BATCH
  try {
    loading.value = true
    const more = await api.getAppEvents(agent.selectedAgent, BATCH, offset.value)
    events.value.push(...more)
    hasMore.value = more.length >= BATCH
  } catch {} finally { loading.value = false }
}

function onClick(e, idx) {
  if (e.screenshot_id) {
    ss.browseTimeline(events.value, idx)
    ss.liveOpen = true
  }
}

defineExpose({ load })
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--purple)"></span> 活动记录</span>
      <span class="card-count" v-if="events.length">{{ events.length }} 条</span>
    </div>
    <div class="card-body">
      <div v-for="(e, idx) in events" :key="e.id"
        class="tl-row" :class="{ clickable: e.screenshot_id }"
        @click="onClick(e, idx)">
        <span class="tl-time">{{ (e.timestamp||'').replace('T',' ').substring(11,16) }}</span>
        <span class="tl-badge" :class="e.event_type === 'chat' ? 'chat' : 'window'">
          {{ e.event_type === 'chat' ? '聊天' : '窗口' }}
        </span>
        <span class="tl-app">{{ e.process_name }}</span>
        <span class="tl-title">{{ e.window_title }}</span>
      </div>
      <div v-if="!events.length && !loading" class="empty">暂无活动</div>
      <div v-if="hasMore && events.length" class="load-more" @click="loadMore">
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
.tl-row { display: flex; align-items: center; gap: 10px; padding: 6px 16px; border-bottom: 1px solid rgba(255,255,255,.02); font-size: 12px; transition: background .1s; }
.tl-row:hover { background: rgba(255,255,255,.03); }
.tl-row.clickable { cursor: pointer; }
.tl-row.clickable:hover { background: rgba(96,165,250,.08); }
.tl-time { font-family: var(--font-mono); font-size: 10px; color: var(--muted); min-width: 44px; flex-shrink: 0; }
.tl-badge { font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px; min-width: 36px; text-align: center; flex-shrink: 0; }
.tl-badge.window { background: rgba(96,165,250,.12); color: var(--blue); }
.tl-badge.chat { background: rgba(167,139,250,.12); color: var(--purple); }
.tl-app { color: var(--amber); font-family: var(--font-mono); font-size: 11px; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.tl-title { color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: var(--muted); padding: 16px; text-align: center; font-size: 11px; }
.load-more { text-align: center; padding: 10px; font-size: 11px; color: var(--accent); cursor: pointer; transition: background .1s; }
.load-more:hover { background: rgba(255,255,255,.04); }
</style>
