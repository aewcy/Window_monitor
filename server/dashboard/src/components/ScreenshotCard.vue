<script setup>
import { useScreenshotStore } from '../stores/screenshot'
import ScreenshotViewer from './ScreenshotViewer.vue'

const ss = useScreenshotStore()
</script>

<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="dot" style="background:var(--blue)"></span> 截图</span>
      <button class="expand-btn" @click="ss.liveOpen = true">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="4,1 1,1 1,4"/><line x1="1" y1="1" x2="6" y2="6"/><polyline points="12,15 15,15 15,12"/><line x1="15" y1="15" x2="10" y2="10"/></svg>
        放大
      </button>
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
.expand-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 10px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer;
  transition: all .15s; display: flex; align-items: center; gap: 4px;
}
.expand-btn:hover { border-color: var(--blue); color: var(--blue); background: rgba(96,165,250,.08); }
</style>
