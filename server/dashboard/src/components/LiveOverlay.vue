<script setup>
import { ref, watch, computed, onUnmounted } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getLiveScreenshotImage, getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)
const currentLiveId = ref(null)
let liveTimer = null
const zoom = ref(1)

const currentItem = computed(() => ss.currentDisplayItem)
const isBrowse = computed(() => ss.displaySource !== 'live')
const isHistory = computed(() => ss.displaySource === 'live' && !ss.liveMode && ss.screenshotList.length > 0)
const showUI = computed(() => isBrowse.value || isHistory.value)

const sourceLabel = computed(() => {
  if (ss.displaySource === 'timeline') return '活动'
  if (ss.displaySource === 'browser') return '浏览'
  if (isHistory.value) return '历史'
  return 'Live'
})

const itemIndex = computed(() => {
  if (isBrowse.value) return `${ss.displayIndex + 1}/${ss.displayItems.length}`
  if (isHistory.value) return `${ss.currentIndex + 1}/${ss.screenshotList.length}`
  return ''
})

const itemTitle = computed(() => {
  if (ss.displaySource === 'timeline' && currentItem.value) {
    return `${currentItem.value.process_name} - ${currentItem.value.window_title}`
  }
  if (ss.displaySource === 'browser' && currentItem.value) {
    return currentItem.value.title || currentItem.value.url
  }
  if (isHistory.value && ss.screenshotList[ss.currentIndex]) {
    const s = ss.screenshotList[ss.currentIndex]
    return (s.timestamp || '').replace('T', ' ')
  }
  return ''
})

async function loadLive() {
  const data = await ss.loadLatest()
  if (data && (data.id || data.image_base64)) {
    if (data.id !== currentLiveId.value) {
      currentLiveId.value = data.id
      imgSrc.value = getLiveScreenshotImage(data) || getScreenshotImage(data.id)
    }
  }
}

function shouldPollLive() {
  return Boolean(ss.liveOpen && ss.displaySource === 'live' && ss.liveMode && agent.selectedAgent)
}

function startLivePolling() {
  stopLivePolling()
  if (!shouldPollLive()) return
  loadLive()
  liveTimer = setInterval(loadLive, ss.livePollMs)
}

function stopLivePolling() {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

function loadBrowseItem() {
  const item = currentItem.value
  if (item && item.screenshot_id) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
    zoom.value = 1
  }
}

function loadHistoryItem() {
  const item = ss.screenshotList[ss.currentIndex]
  if (item && item.id) {
    imgSrc.value = getScreenshotImage(item.id)
    zoom.value = 1
  }
}

async function ensureHistory() {
  if (!ss.screenshotList.length) {
    await ss.loadHistory()
  }
  loadHistoryItem()
}

async function syncOpenImage() {
  if (!ss.liveOpen) return
  zoom.value = 1
  if (isBrowse.value) {
    stopLivePolling()
    loadBrowseItem()
    return
  }
  if (!ss.liveMode) {
    stopLivePolling()
    await ensureHistory()
    return
  }
  currentLiveId.value = null
  startLivePolling()
}

function close() {
  ss.liveOpen = false
}

async function setSnapshotMode(mode) {
  if (mode === 'live') {
    ss.goLive()
    currentLiveId.value = null
    startLivePolling()
    return
  }

  ss.goHistory()
  stopLivePolling()
  await ensureHistory()
}

watch(() => ss.liveOpen, v => {
  if (v) syncOpenImage()
  else stopLivePolling()
})

watch(() => ss.currentDisplayItem, item => {
  if (item && item.screenshot_id && ss.liveOpen && isBrowse.value) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
    zoom.value = 1
  }
}, { immediate: true })

watch(() => ss.currentIndex, () => {
  if (isHistory.value && ss.liveOpen) {
    loadHistoryItem()
  }
})

watch(() => [agent.selectedAgent, agent.selectedMonitor, ss.liveMode, ss.displaySource], syncOpenImage)
watch(() => ss.livePollMs, () => {
  if (shouldPollLive()) startLivePolling()
})

onUnmounted(stopLivePolling)

function prev() {
  if (isHistory.value) {
    if (ss.currentIndex > 0) ss.currentIndex--
    else ss.currentIndex = ss.screenshotList.length - 1
  } else {
    ss.prev()
  }
}

function next() {
  if (isHistory.value) {
    if (ss.currentIndex < ss.screenshotList.length - 1) ss.currentIndex++
    else ss.currentIndex = 0
  } else {
    ss.next()
  }
}

function onWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    zoom.value = Math.min(3, Math.max(0.3, zoom.value + delta))
  } else if (showUI.value) {
    if (e.deltaY > 0) next()
    else if (e.deltaY < 0) prev()
  }
}
</script>

<template>
  <div class="live-overlay" :class="{ open: ss.liveOpen }" @click.self="close" @wheel.prevent="onWheel">
    <div class="live-box">
      <div class="live-header">
        <span class="live-title">
          <span v-if="!showUI" class="live-dot"></span>
          <span v-if="!showUI" class="live-text">Live</span>
          <span v-else class="browse-tag">{{ sourceLabel }} {{ itemIndex }}</span>
          <span class="agent-name">{{ agent.selectedAgent }}</span>
        </span>
        <div class="header-actions">
          <div class="mode-tabs">
            <button :class="{ active: ss.displaySource === 'live' && ss.liveMode }" @click="setSnapshotMode('live')">
              <span class="live-dot-sm"></span> 实时
            </button>
            <button :class="{ active: ss.displaySource === 'live' && !ss.liveMode }" @click="setSnapshotMode('history')">
              历史
            </button>
          </div>
          <span class="zoom-label" v-if="zoom !== 1">{{ Math.round(zoom * 100) }}%</span>
          <button class="close-btn" @click="close">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
            关闭
          </button>
        </div>
      </div>
      <div class="live-body">
        <img v-if="imgSrc" :src="imgSrc" class="live-img" :key="imgSrc"
          :style="{ transform: `scale(${zoom})`, transition: 'transform .15s' }" />
        <div v-else class="placeholder"><span class="big">[ ]</span>暂无截图</div>
        <div class="mon-chips" v-if="agent.monitorTotal > 1 && !showUI">
          <button v-for="i in agent.monitorTotal" :key="i"
            class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
            @click="agent.selectMonitor(i-1)">屏{{ i }}</button>
        </div>
        <div class="item-title" v-if="itemTitle">
          <span class="title-text">{{ itemTitle }}</span>
        </div>
        <div class="nav" v-if="showUI && (ss.displayItems.length > 1 || ss.screenshotList.length > 1)">
          <button class="nav-pill" @click="prev">上一张</button>
          <button class="nav-pill" @click="next">下一张</button>
        </div>
        <div class="wheel-hint" v-if="showUI">
          <span>滚轮切换</span>
          <span>Ctrl+滚轮缩放</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.live-overlay {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(8px);
  opacity: 0; pointer-events: none; transition: opacity .25s cubic-bezier(0.22,1,0.36,1);
}
.live-overlay.open { opacity: 1; pointer-events: auto; }
.live-box {
  width: 70vw; height: 70vh; background: var(--ground);
  border: 1px solid var(--hairline); border-radius: var(--radius-lg);
  overflow: hidden; display: flex; flex-direction: column;
  box-shadow: 0 32px 80px rgba(0,0,0,0.6);
  transform: scale(0.92); transition: transform .3s cubic-bezier(0.22,1,0.36,1);
}
.live-overlay.open .live-box { transform: scale(1); }
.live-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--hairline); flex-shrink: 0;
}
.live-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 1.5s infinite; }
.live-dot-sm { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 1.5s infinite; }
.live-text { color: var(--green); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; font-weight: 700; }
.browse-tag { font-family: var(--font-mono); color: var(--purple); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.agent-name { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.mode-tabs {
  display: flex; align-items: center; gap: 2px;
  padding: 2px; border: 1px solid var(--hairline); border-radius: 7px;
  background: rgba(0,0,0,.18);
}
.mode-tabs button {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  display: flex; align-items: center; gap: 5px;
  border: 0; border-radius: 5px; padding: 3px 9px;
  background: transparent; color: var(--text-secondary); cursor: pointer;
}
.mode-tabs button:hover { color: var(--text); background: rgba(255,255,255,.06); }
.mode-tabs button.active { color: var(--green); background: rgba(74,222,128,.12); }
.zoom-label {
  font-family: var(--font-mono); font-size: 10px; color: var(--amber);
  padding: 2px 8px; background: rgba(251,191,36,.1); border-radius: 4px;
}
.close-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 4px;
}
.close-btn:hover { border-color: var(--red); color: var(--red); }
.live-body { flex: 1; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.3); position: relative; overflow: hidden; }
.live-img { max-width: 100%; max-height: 100%; object-fit: contain; transform-origin: center center; }
.placeholder { text-align: center; color: var(--muted); }
.placeholder .big { font-size: 64px; opacity: 0.1; display: block; margin-bottom: 12px; }
.mon-chips { position: absolute; top: 12px; left: 16px; display: flex; gap: 6px; }
.mon-chip {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 10px; border-radius: 20px; border: 1px solid var(--hairline);
  color: var(--muted); background: rgba(0,0,0,0.5); cursor: pointer; transition: all .15s;
}
.mon-chip:hover { border-color: var(--blue); color: var(--blue); }
.mon-chip.active { border-color: var(--blue); color: var(--blue); background: rgba(96,165,250,.15); }
.item-title {
  position: absolute; bottom: 56px; left: 50%; transform: translateX(-50%);
  max-width: 80%; text-align: center;
}
.title-text {
  font-family: var(--font-mono); font-size: 12px; font-weight: 500;
  padding: 5px 16px; background: rgba(0,0,0,0.65); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary);
  backdrop-filter: blur(8px); display: inline-block;
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.nav { position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
.nav-pill {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  padding: 6px 18px; background: rgba(255,255,255,0.08); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary); cursor: pointer; backdrop-filter: blur(8px); transition: all .15s;
}
.nav-pill:hover { background: rgba(255,255,255,0.14); color: var(--text); border-color: rgba(255,255,255,0.2); }
.wheel-hint {
  position: absolute; bottom: 16px; right: 16px;
  display: flex; gap: 12px; font-family: var(--font-mono); font-size: 9px; color: var(--muted);
  opacity: 0.6;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
