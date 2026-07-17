<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getLiveScreenshotImage, getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)
const timestamp = ref('')
const currentId = ref(null)
const placeholderText = ref('选择被控端查看截图')
let liveTimer = null
let requestSeq = 0
const preferFreshLive = ref(true)

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

function resetLiveView(message = '正在切换...') {
  requestSeq += 1
  imgSrc.value = null
  timestamp.value = ''
  currentId.value = null
  placeholderText.value = message
  preferFreshLive.value = true
}

function makeSnapshot() {
  return {
    seq: requestSeq + 1,
    agentName: agent.selectedAgent,
    monitor: agent.selectedMonitor,
    source: ss.displaySource,
  }
}

function isSnapshotCurrent(snapshot) {
  return (
    snapshot.seq === requestSeq
    && agent.selectedAgent === snapshot.agentName
    && agent.selectedMonitor === snapshot.monitor
    && ss.displaySource === snapshot.source
  )
}

async function load() {
  if (!agent.selectedAgent) return
  const snapshot = makeSnapshot()
  requestSeq = snapshot.seq
  let data

  if (preferFreshLive.value) {
    // 切屏首帧优先拿目标屏 fresh 帧；延迟流准备好前不能立刻切走。
    const freshData = await ss.loadLatest({
      agentName: snapshot.agentName,
      monitor: snapshot.monitor,
      allowStoredFallback: false,
      preferFresh: true,
    })
    if (!isSnapshotCurrent(snapshot)) return

    const delayedData = await ss.loadLatest({
      agentName: snapshot.agentName,
      monitor: snapshot.monitor,
      allowStoredFallback: false,
      preferFresh: false,
    })
    if (!isSnapshotCurrent(snapshot)) return

    data = delayedData || freshData
    if (delayedData) preferFreshLive.value = false
  } else {
    data = await ss.loadLatest({
      agentName: snapshot.agentName,
      monitor: snapshot.monitor,
      allowStoredFallback: true,
      preferFresh: false,
    })
    if (!isSnapshotCurrent(snapshot)) return
    if (!data) preferFreshLive.value = true
  }

  if (!data && Number(snapshot.monitor) > 0) {
    const primaryData = await ss.loadLatest({
      agentName: snapshot.agentName,
      monitor: 0,
      allowStoredFallback: true,
      preferFresh: preferFreshLive.value,
    })
    if (primaryData && isSnapshotCurrent(snapshot)) {
      agent.selectMonitor(0)
    }
    return
  }
  if (data && (data.id || data.image_base64)) {
    if (data.id !== currentId.value) {
      currentId.value = data.id
      imgSrc.value = getLiveScreenshotImage(data) || getScreenshotImage(data.id)
    }
    const label = String(data.id || '').startsWith('live:') ? '实时' : '最近'
    timestamp.value = label + ' ' + new Date(data.timestamp).toTimeString().slice(0, 8)
    placeholderText.value = '等待实时画面'
  } else if (!imgSrc.value) {
    placeholderText.value = '等待实时画面'
  }
}

function shouldPollLive() {
  return Boolean(agent.selectedAgent && ss.displaySource === 'live')
}

function startLivePolling() {
  stopLivePolling()
  if (!shouldPollLive()) return
  load()
  liveTimer = setInterval(load, ss.livePollMs)
}

function stopLivePolling() {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

watch(() => agent.selectedAgent, () => {
  if (agent.selectedAgent) {
    stopLivePolling()
    resetLiveView('正在切换被控机...')
    ss.goLive()
    ss.resetLiveInterval(null)
    startLivePolling()
  }
})
watch(() => agent.selectedMonitor, () => {
  stopLivePolling()
  resetLiveView('正在切换屏幕...')
  ss.resetLiveInterval(null)
  if (shouldPollLive()) startLivePolling()
})
watch(() => ss.displaySource, startLivePolling)
watch(() => ss.livePollMs, startLivePolling)

defineExpose({ load })
onMounted(startLivePolling)
onUnmounted(stopLivePolling)
</script>

<template>
  <div class="screenshot-stage">
    <img v-if="imgSrc" :src="imgSrc" class="screenshot-img" :key="imgSrc" />
    <div v-else class="placeholder">
      <span class="big">[ ]</span>
      {{ placeholderText }}
    </div>
    <div class="monitor-chips" v-if="agent.monitorTotal > 1">
      <button v-for="i in agent.monitorTotal" :key="i"
        class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
        @click="agent.selectMonitor(i-1)">
        {{ `屏${i}` }}
      </button>
    </div>
    <div class="top-right">
      <span class="fps-badge" v-if="fpsLabel()">{{ fpsLabel() }}</span>
      <span class="timestamp" v-if="timestamp">{{ timestamp }}</span>
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
.timestamp {
  font-family: var(--font-mono); font-size: 10px; color: var(--green); font-weight: 500;
  padding: 2px 8px; background: rgba(0,0,0,0.4); border-radius: 6px;
}
</style>
