<script setup>
import { computed, ref } from 'vue'
import { sendAgentCommand } from '../api'
import { useAgentStore } from '../stores/agent'
import { useScreenshotStore } from '../stores/screenshot'
import ScreenshotViewer from './ScreenshotViewer.vue'

const ss = useScreenshotStore()
const agent = useAgentStore()
const commandLoading = ref(false)

const selectedAgent = computed(() => agent.selectedAgentData)
const capturePaused = computed(() => selectedAgent.value?.control_status === 'paused')
const canControl = computed(() => Boolean(selectedAgent.value?.name) && selectedAgent.value?.status === 'online')

async function toggleCapture() {
  const target = selectedAgent.value
  if (!target || commandLoading.value) return
  commandLoading.value = true
  try {
    await sendAgentCommand(target.name, capturePaused.value ? 'resume_capture' : 'pause_capture')
    await agent.loadAgents()
  } catch (e) {
    console.error('Agent command failed:', e)
  } finally {
    commandLoading.value = false
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--blue)"></span> Live</span>
      <div class="card-actions">
        <button
          class="capture-btn"
          :class="{ paused: capturePaused }"
          :disabled="!canControl || commandLoading"
          :title="canControl ? (capturePaused ? '恢复采集' : '暂停采集') : '被控机离线，无法控制采集'"
          @click="toggleCapture"
        >
          {{ capturePaused ? '恢复采集' : '暂停采集' }}
        </button>
        <button class="expand-btn" @click="ss.liveOpen = true">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="4,1 1,1 1,4"/><line x1="1" y1="1" x2="6" y2="6"/><polyline points="12,15 15,15 15,12"/><line x1="15" y1="15" x2="10" y2="10"/></svg>
          放大
        </button>
      </div>
    </div>
    <div class="card-body">
      <ScreenshotViewer />
    </div>
  </div>
</template>

<style scoped>
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-lg); overflow: hidden; display: flex; flex-direction: column; }
.card-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--hairline); flex-shrink: 0; }
.card-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.card-body { flex: 1; overflow: hidden; min-height: 0; }
.card-actions { display: flex; align-items: center; gap: 8px; }
.capture-btn,
.expand-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 10px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer;
  transition: all .15s; display: flex; align-items: center; gap: 4px;
}
.capture-btn:hover:not(:disabled),
.expand-btn:hover { border-color: var(--blue); color: var(--blue); background: rgba(96,165,250,.08); }
.capture-btn.paused { border-color: var(--yellow); color: var(--yellow); background: rgba(245,158,11,.08); }
.capture-btn:disabled { opacity: .45; cursor: not-allowed; }
</style>
