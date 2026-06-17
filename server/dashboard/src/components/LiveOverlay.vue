<script setup>
import { ref, watch } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)

async function load() {
  const data = await ss.loadLatest()
  if (data && data.id) {
    imgSrc.value = getScreenshotImage(data.id)
  }
}

watch(() => ss.liveOpen, (v) => { if (v) load() })

function close() { ss.liveOpen = false }
</script>

<template>
  <div class="live-overlay" :class="{ open: ss.liveOpen }" @click.self="close">
    <div class="live-box">
      <div class="live-header">
        <span class="live-title">
          <span class="live-dot"></span>
          <span class="live-text">Live</span>
          <span class="agent-name">{{ agent.selectedAgent }}</span>
        </span>
        <button class="close-btn" @click="close">
          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
          关闭
        </button>
      </div>
      <div class="live-body">
        <img v-if="imgSrc" :src="imgSrc" class="live-img" :key="imgSrc" />
        <div v-else class="placeholder"><span class="big">[ ]</span>实时截图画面</div>
        <div class="mon-chips" v-if="agent.monitorTotal > 1">
          <button v-for="i in agent.monitorTotal" :key="i"
            class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
            @click="agent.selectMonitor(i-1)">屏{{ i }}</button>
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
.live-text { color: var(--green); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; font-weight: 700; }
.agent-name { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.close-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 4px;
}
.close-btn:hover { border-color: var(--red); color: var(--red); }
.live-body { flex: 1; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.3); position: relative; }
.live-img { max-width: 100%; max-height: 100%; object-fit: contain; }
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
</style>
