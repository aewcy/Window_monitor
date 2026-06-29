<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useAgentStore } from './stores/agent'
import { useScreenshotStore } from './stores/screenshot'
import { useThemeStore } from './stores/theme'
import { usePolling } from './composables/usePolling'

import AppHeader from './components/AppHeader.vue'
import AgentStrip from './components/AgentStrip.vue'
import ScreenshotCard from './components/ScreenshotCard.vue'
import TimelineCard from './components/TimelineCard.vue'
import BrowserCard from './components/BrowserCard.vue'
import LogCard from './components/LogCard.vue'
import StatsBar from './components/StatsBar.vue'
import LiveOverlay from './components/LiveOverlay.vue'
import GridOverlay from './components/GridOverlay.vue'
import ThemePicker from './components/ThemePicker.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'

const agent = useAgentStore()
const ss = useScreenshotStore()
const theme = useThemeStore()
const { startSlow, stopAll } = usePolling()

const timelineRef = ref(null)
const browserRef = ref(null)
const logRef = ref(null)
const statsRef = ref(null)

function refreshSlow() {
  timelineRef.value?.refresh?.()
  browserRef.value?.load()
  logRef.value?.load()
  statsRef.value?.load()
}

onMounted(async () => {
  theme.init()
  await agent.loadAgents()
  startSlow(refreshSlow, 5000)
  document.addEventListener('keydown', onKey)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
})

onUnmounted(stopAll)

watch(() => [agent.selectedAgent, agent.selectedMonitor], () => {
  timelineRef.value?.load()
  browserRef.value?.load()
  logRef.value?.load()
  statsRef.value?.load()
})

function onKey(e) {
  // ESC 逐层退出: overlay → 网格 → 主题面板
  if (e.key === 'Escape') {
    if (ss.liveOpen) {
      ss.liveOpen = false
    } else if (ss.gridMode) {
      ss.gridMode = false
      ss.goLive()
    } else {
      theme.closePanel()
    }
    return
  }
  if (e.key === 'g' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ss.gridMode = !ss.gridMode }
  if (e.key === 'r' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); refreshSlow() }
}
</script>

<template>
  <div class="backdrop"></div>
  <AppHeader />
  <AgentStrip />
  <div class="main">
    <ScreenshotCard />
    <TimelineCard ref="timelineRef" />
    <BrowserCard ref="browserRef" />
    <LogCard ref="logRef" />
  </div>
  <StatsBar ref="statsRef" />
  <LiveOverlay />
  <GridOverlay />
  <ThemePicker />
  <ConfirmDialog />
</template>

<style scoped>
.backdrop {
  position: fixed; top: -40%; left: -20%; width: 140%; height: 80%;
  background: radial-gradient(ellipse at 30% 50%, rgba(255,99,99,0.08) 0%, transparent 50%),
              radial-gradient(ellipse at 70% 30%, rgba(167,139,250,0.06) 0%, transparent 50%),
              radial-gradient(ellipse at 50% 80%, rgba(96,165,250,0.05) 0%, transparent 50%);
  filter: blur(80px); pointer-events: none; z-index: 0; transition: background .6s ease;
}
.main {
  display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;
  gap: 12px; padding: 12px 24px 48px; position: relative; z-index: 1;
  height: calc(100vh - 100px);
}
</style>
