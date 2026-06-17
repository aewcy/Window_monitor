<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)
const timestamp = ref('')

const fpsLabel = () => {
  const d = agent.selectedAgentData
  if (!d || !d.screenshot_interval) return null
  const v = d.screenshot_interval
  if (v <= 0.5) return '4fps'
  if (v <= 1.5) return '1fps'
  if (v <= 6) return '1/5s'
  if (v <= 61) return '1/min'
  return null
}

// 当前显示的标题（时间线/浏览器模式）
const itemTitle = computed(() => {
  if (ss.displaySource === 'timeline') {
    const e = ss.currentDisplayItem
    return e ? `${e.process_name} — ${e.window_title}` : ''
  }
  if (ss.displaySource === 'browser') {
    const r = ss.currentDisplayItem
    return r ? (r.title || r.url) : ''
  }
  return ''
})

const itemIndex = computed(() => {
  if (ss.displaySource === 'live') return ''
  return `${ss.displayIndex + 1}/${ss.displayItems.length}`
})

const sourceLabel = computed(() => {
  if (ss.displaySource === 'timeline') return '活动'
  if (ss.displaySource === 'browser') return '浏览'
  return ''
})

async function load() {
  const data = await ss.loadLatest()
  if (data && data.id) {
    imgSrc.value = getScreenshotImage(data.id)
    timestamp.value = '实时 ' + new Date(data.timestamp).toTimeString().slice(0, 8)
  }
}

// 监听 displayItems 中当前项的变化
watch(() => ss.currentDisplayItem, (item) => {
  if (item && item.screenshot_id) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
    timestamp.value = ''
  }
}, { immediate: true })

// 监听 liveMode 或 displaySource 变化 — 切回实时模式时重新加载
watch([() => ss.liveMode, () => ss.displaySource], ([live, src]) => {
  if (live && src === 'live') {
    load()
  }
})

watch(() => agent.selectedAgent, () => {
  if (agent.selectedAgent) {
    ss.goLive()  // 切换 Agent 时回到实时模式
    load()
  }
})
watch(() => agent.selectedMonitor, () => { if (agent.selectedAgent) load() })

defineExpose({ load })
onMounted(() => { if (agent.selectedAgent) load() })
</script>

<template>
  <div class="screenshot-stage">
    <img v-if="imgSrc" :src="imgSrc" class="screenshot-img" :key="imgSrc" />
    <div v-else class="placeholder">
      <span class="big">[ ]</span>
      选择被控端查看截图
    </div>
    <div class="monitor-chips" v-if="agent.monitorTotal > 1">
      <button v-for="i in agent.monitorTotal" :key="i"
        class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
        @click="agent.selectMonitor(i-1)">
        屏{{ i }}
      </button>
      <button class="mon-chip" :class="{ active: agent.selectedMonitor === null }"
        @click="agent.selectMonitor(null)">全部</button>
    </div>
    <div class="top-right">
      <span class="fps-badge" v-if="fpsLabel() && ss.displaySource === 'live'">{{ fpsLabel() }}</span>
      <span class="source-badge" v-if="sourceLabel">{{ sourceLabel }} {{ itemIndex }}</span>
      <span class="timestamp" v-if="timestamp">{{ timestamp }}</span>
    </div>
    <div class="item-title" v-if="itemTitle">
      <span class="title-text">{{ itemTitle }}</span>
    </div>
    <div class="nav">
      <button class="nav-pill" @click="ss.prev()">◀ 上一个</button>
      <button class="nav-pill" @click="ss.next()">下一个 ▶</button>
    </div>
  </div>
</template>

<style scoped>
.screenshot-stage { display: flex; align-items: center; justify-content: center; height: 100%; background: rgba(0,0,0,0.3); position: relative; }
.screenshot-img { max-width: 100%; max-height: 100%; object-fit: contain; }
.placeholder { text-align: center; color: var(--muted); }
.placeholder .big { font-size: 40px; opacity: 0.15; display: block; margin-bottom: 8px; }
.monitor-chips { position: absolute; top: 10px; left: 12px; display: flex; gap: 4px; }
.mon-chip {
  font-family: var(--font-mono); font-size: 9px; font-weight: 500;
  padding: 2px 8px; border-radius: 20px; border: 1px solid var(--hairline);
  color: var(--muted); background: rgba(0,0,0,0.4); backdrop-filter: blur(4px);
  cursor: pointer; transition: all .15s;
}
.mon-chip:hover { border-color: var(--blue); color: var(--blue); }
.mon-chip.active { border-color: var(--blue); color: var(--blue); background: rgba(96,165,250,.15); }
.top-right {
  position: absolute; top: 10px; right: 12px;
  display: flex; gap: 6px; align-items: center;
}
.fps-badge {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 2px 8px; background: rgba(0,0,0,0.5); border: 1px solid var(--hairline);
  border-radius: 6px; color: var(--amber);
}
.source-badge {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 2px 8px; background: rgba(0,0,0,0.5); border: 1px solid var(--hairline);
  border-radius: 6px; color: var(--purple);
}
.timestamp {
  font-family: var(--font-mono); font-size: 10px; color: var(--green); font-weight: 500;
  padding: 2px 8px; background: rgba(0,0,0,0.4); border-radius: 6px;
}
.item-title {
  position: absolute; bottom: 44px; left: 50%; transform: translateX(-50%);
  max-width: 80%; text-align: center;
}
.title-text {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  padding: 4px 14px; background: rgba(0,0,0,0.6); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary);
  backdrop-filter: blur(8px);
  display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.nav { position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 4px; }
.nav-pill {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; background: rgba(255,255,255,0.08); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary); cursor: pointer; backdrop-filter: blur(8px); transition: all .15s;
}
.nav-pill:hover { background: rgba(255,255,255,0.14); color: var(--text); }
</style>
