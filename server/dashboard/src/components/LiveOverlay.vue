<script setup>
import { ref, watch, computed, onUnmounted } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getLiveScreenshotImage, getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)
const currentLiveId = ref(null)
const currentLiveData = ref(null)
const placeholderText = ref('等待实时画面')
let liveTimer = null
let liveRequestSeq = 0
const preferFreshLive = ref(true)
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const imageStageEl = ref(null)
const dragging = ref(false)
const imageMetaOpen = ref(false)
let dragStart = null

const currentItem = computed(() => ss.currentDisplayItem)
const isBrowse = computed(() => ss.displaySource !== 'live')
const showUI = computed(() => isBrowse.value)

const sourceLabel = computed(() => {
  if (ss.displaySource === 'timeline') return '活动'
  if (ss.displaySource === 'browser') return '浏览'
  return 'Live'
})

const itemIndex = computed(() => {
  if (isBrowse.value) return `${ss.displayIndex + 1}/${ss.displayItems.length}`
  return ''
})

const itemTitle = computed(() => {
  if (ss.displaySource === 'timeline' && currentItem.value) {
    return `${currentItem.value.process_name} - ${currentItem.value.window_title}`
  }
  if (ss.displaySource === 'browser' && currentItem.value) {
    return currentItem.value.title || currentItem.value.url
  }
  return ''
})

const imageMetaSource = computed(() => {
  if (isBrowse.value) return currentItem.value || {}
  return currentLiveData.value || {}
})

const imageMetaRows = computed(() => {
  const item = imageMetaSource.value || {}
  const rows = [
    ['网址', item.foreground_url || item.url || ''],
    ['程序', item.foreground_process_name || item.process_name || ''],
    ['标题', item.foreground_window_title || item.window_title || item.title || ''],
    ['规则', item.matched_rule_type ? `${item.matched_rule_type}: ${item.matched_rule_pattern || ''}` : ''],
    ['策略', item.save_policy_phase || ''],
    ['被控机', item.agent_name || agent.selectedAgent || ''],
    ['屏幕', item.monitor_total > 1 ? `屏${Number(item.monitor_index || 0) + 1}/${item.monitor_total}` : ''],
    ['时间', (item.timestamp || item.screenshot_time || '').replace('T', ' ')],
  ]
  return rows.filter(([, value]) => String(value || '').trim())
})

const imagePrimaryUrl = computed(() => {
  const item = imageMetaSource.value || {}
  return item.foreground_url || item.url || ''
})

function copyImageUrl() {
  if (!imagePrimaryUrl.value) return
  navigator.clipboard?.writeText(imagePrimaryUrl.value).catch(() => {})
}

async function loadLive() {
  const snapshot = {
    seq: liveRequestSeq + 1,
    agentName: agent.selectedAgent,
    monitor: agent.selectedMonitor,
    source: ss.displaySource,
    open: ss.liveOpen,
  }
  liveRequestSeq = snapshot.seq
  const data = await ss.loadLatest({
    agentName: snapshot.agentName,
    monitor: snapshot.monitor,
    allowStoredFallback: true,
    preferFresh: preferFreshLive.value,
  })
  if (
    snapshot.seq !== liveRequestSeq
    || !snapshot.open
    || !ss.liveOpen
    || ss.displaySource !== snapshot.source
    || agent.selectedAgent !== snapshot.agentName
    || agent.selectedMonitor !== snapshot.monitor
  ) {
    return
  }
  if (!data && Number(snapshot.monitor) > 0) {
    const primaryData = await ss.loadLatest({
      agentName: snapshot.agentName,
      monitor: 0,
      allowStoredFallback: true,
      preferFresh: preferFreshLive.value,
    })
    if (
      primaryData
      && snapshot.seq === liveRequestSeq
      && ss.liveOpen
      && ss.displaySource === snapshot.source
      && agent.selectedAgent === snapshot.agentName
      && agent.selectedMonitor === snapshot.monitor
    ) {
      agent.selectMonitor(0)
    }
    return
  }
  if (data && (data.id || data.image_base64)) {
    if (data.id !== currentLiveId.value) {
      currentLiveId.value = data.id
      imgSrc.value = getLiveScreenshotImage(data) || getScreenshotImage(data.id)
    }
    currentLiveData.value = data
    placeholderText.value = '等待实时画面'
    if (String(data.id || '').startsWith('live:')) preferFreshLive.value = false
  } else if (!imgSrc.value) {
    placeholderText.value = '等待实时画面'
  }
}

function resetLiveView(message = '正在切换...') {
  liveRequestSeq += 1
  currentLiveId.value = null
  currentLiveData.value = null
  imgSrc.value = null
  placeholderText.value = message
  preferFreshLive.value = true
  imageMetaOpen.value = false
  resetImageTransform()
}

function shouldPollLive() {
  return Boolean(ss.liveOpen && ss.displaySource === 'live' && agent.selectedAgent && !document.hidden)
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
  liveRequestSeq += 1
  const item = currentItem.value
  if (item && item.screenshot_id) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
    currentLiveData.value = null
    imageMetaOpen.value = false
    resetImageTransform()
  } else {
    imgSrc.value = null
    currentLiveData.value = null
    placeholderText.value = '暂无截图'
  }
}

async function syncOpenImage() {
  if (!ss.liveOpen) return
  resetImageTransform()
  if (isBrowse.value) {
    stopLivePolling()
    loadBrowseItem()
    return
  }
  stopLivePolling()
  resetLiveView('正在切换...')
  ss.resetLiveInterval(null)
  startLivePolling()
}

function close() {
  ss.liveOpen = false
  if (ss.displaySource !== 'live') {
    ss.goLive()
  }
}

watch(() => ss.liveOpen, v => {
  if (v) syncOpenImage()
  else stopLivePolling()
})

watch(() => ss.currentDisplayItem, item => {
  if (item && item.screenshot_id && ss.liveOpen && isBrowse.value) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
    resetImageTransform()
  }
}, { immediate: true })

watch(() => [agent.selectedAgent, agent.selectedMonitor, ss.displaySource], syncOpenImage)
watch(() => ss.livePollMs, () => {
  if (shouldPollLive()) startLivePolling()
})

function onVisibilityChange() {
  if (shouldPollLive()) startLivePolling()
  else stopLivePolling()
}

document.addEventListener('visibilitychange', onVisibilityChange)

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopLivePolling()
})

function prev() {
  if (isBrowse.value) {
    ss.prev()
  }
}

function next() {
  if (isBrowse.value) {
    ss.next()
  }
}

function onWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const oldZoom = zoom.value
    const nextZoom = Math.min(3, Math.max(0.3, oldZoom + (e.deltaY > 0 ? -0.1 : 0.1)))
    if (nextZoom === oldZoom) return

    const rect = imageStageEl.value?.getBoundingClientRect()
    if (rect) {
      const pointerX = e.clientX - rect.left - rect.width / 2
      const pointerY = e.clientY - rect.top - rect.height / 2
      panX.value = pointerX - ((pointerX - panX.value) / oldZoom) * nextZoom
      panY.value = pointerY - ((pointerY - panY.value) / oldZoom) * nextZoom
    }
    zoom.value = nextZoom
  } else if (showUI.value) {
    if (e.deltaY > 0) next()
    else if (e.deltaY < 0) prev()
  }
}

function resetImageTransform() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
  dragging.value = false
  dragStart = null
}

function onPointerDown(e) {
  if (e.button !== 0 || !imgSrc.value) return
  e.preventDefault()
  dragging.value = true
  dragStart = {
    pointerId: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    panX: panX.value,
    panY: panY.value,
  }
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onPointerMove(e) {
  if (!dragging.value || !dragStart) return
  e.preventDefault()
  panX.value = dragStart.panX + e.clientX - dragStart.x
  panY.value = dragStart.panY + e.clientY - dragStart.y
}

function stopDrag(e) {
  if (dragStart && e?.pointerId === dragStart.pointerId) {
    e.currentTarget?.releasePointerCapture?.(e.pointerId)
  }
  dragging.value = false
  dragStart = null
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
          <div v-if="!showUI" class="mode-pill"><span class="live-dot-sm"></span> 实时</div>
          <span class="zoom-label" v-if="zoom !== 1">{{ Math.round(zoom * 100) }}%</span>
          <button class="close-btn" @click="close">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
            关闭
          </button>
        </div>
      </div>
      <div class="live-body">
        <div
          ref="imageStageEl"
          class="image-stage"
          :class="{ dragging }"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="stopDrag"
          @pointercancel="stopDrag">
          <img v-if="imgSrc" :src="imgSrc" class="live-img" :key="imgSrc"
            draggable="false"
            :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})` }" />
          <div v-else class="placeholder"><span class="big">[ ]</span>{{ placeholderText }}</div>
          <div class="image-meta" v-if="imgSrc && imageMetaRows.length" @pointerdown.stop @click.stop>
            <button
              class="meta-corner"
              :class="{ open: imageMetaOpen }"
              title="查看图片网址和程序信息"
              @click="imageMetaOpen = !imageMetaOpen">
              <span></span>
            </button>
            <div class="meta-panel" v-if="imageMetaOpen">
              <div class="meta-head">
                <span>图片信息</span>
                <button v-if="imagePrimaryUrl" class="copy-url" @click="copyImageUrl">复制 URL</button>
              </div>
              <div class="meta-row" v-for="[label, value] in imageMetaRows" :key="label">
                <span class="meta-label">{{ label }}</span>
                <span class="meta-value" :title="value">{{ value }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="mon-chips" v-if="agent.monitorTotal > 1 && !showUI">
          <button v-for="i in agent.monitorTotal" :key="i"
            class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
            @click="agent.selectMonitor(i-1)">屏{{ i }}</button>
        </div>
        <div class="item-title" v-if="itemTitle">
          <span class="title-text">{{ itemTitle }}</span>
        </div>
        <div class="nav" v-if="showUI && ss.displayItems.length > 1">
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
.mode-pill {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  display: flex; align-items: center; gap: 5px;
  border: 1px solid var(--hairline); border-radius: 7px; padding: 5px 10px;
  background: rgba(74,222,128,.12); color: var(--green);
}
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
.live-body { flex: 1; background: rgba(0,0,0,0.3); position: relative; overflow: hidden; }
.image-stage {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  cursor: grab; user-select: none; touch-action: none; overflow: hidden;
}
.image-stage.dragging { cursor: grabbing; }
.live-img {
  max-width: 100%; max-height: 100%; object-fit: contain; transform-origin: center center;
  transition: transform .12s; pointer-events: none;
}
.image-stage.dragging .live-img { transition: none; }
.image-meta {
  position: absolute; right: 14px; bottom: 14px; z-index: 5;
  display: flex; align-items: flex-end; justify-content: flex-end;
}
.meta-corner {
  width: 28px; height: 28px; border: 1px solid rgba(255,255,255,.2);
  border-radius: 8px; background: rgba(0,0,0,.64); color: var(--text-secondary);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(8px); transition: all .15s;
}
.meta-corner:hover, .meta-corner.open { border-color: var(--blue); color: var(--blue); background: rgba(15,23,42,.86); }
.meta-corner span {
  width: 0; height: 0; border-left: 8px solid currentColor; border-top: 8px solid transparent;
  transform: rotate(45deg); transform-origin: center;
}
.meta-panel {
  position: absolute; right: 0; bottom: 36px;
  width: min(460px, calc(70vw - 48px)); max-height: min(42vh, 360px); overflow: auto;
  padding: 12px; border: 1px solid rgba(255,255,255,.14); border-radius: 12px;
  background: rgba(10,14,22,.92); box-shadow: 0 18px 50px rgba(0,0,0,.45);
  backdrop-filter: blur(12px);
}
.meta-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; color: var(--text); font-size: 12px; font-weight: 700; }
.copy-url {
  border: 1px solid var(--hairline); border-radius: 6px; background: rgba(255,255,255,.06);
  color: var(--text-secondary); cursor: pointer; font-family: var(--font-mono); font-size: 10px; padding: 3px 8px;
}
.copy-url:hover { border-color: var(--blue); color: var(--blue); }
.meta-row {
  display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 10px;
  padding: 6px 0; border-top: 1px solid rgba(255,255,255,.06);
  font-size: 11px; line-height: 1.35;
}
.meta-label { color: var(--muted); font-family: var(--font-mono); }
.meta-value { color: var(--text-secondary); overflow-wrap: anywhere; word-break: break-word; }
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
