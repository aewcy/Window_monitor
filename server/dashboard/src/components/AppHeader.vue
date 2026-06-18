<script setup>
import { useScreenshotStore } from '../stores/screenshot'
import { usePolling } from '../composables/usePolling'
import CalendarPicker from './CalendarPicker.vue'

const ss = useScreenshotStore()
const { startFast, stopFast } = usePolling()
</script>

<template>
  <div class="header">
    <div class="header-left">
      <div class="logo"><div class="icon">M</div> Monitor</div>
    </div>
    <div class="header-right">
      <CalendarPicker />
      <button class="header-chip" :class="{ active: ss.liveMode }" @click="ss.liveMode = !ss.liveMode">
        <span class="live-dot"></span>
        {{ ss.liveMode ? '实时模式' : '历史模式' }}
        <span class="shortcut">⌘L</span>
      </button>
      <button class="header-chip" :class="{ active: ss.gridMode }" @click="ss.gridMode = !ss.gridMode">
        网格视图 <span class="shortcut">⌘G</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.header {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 24px; background: rgba(15,15,17,0.8);
  backdrop-filter: blur(20px); border-bottom: 1px solid var(--hairline);
}
.header-left { display: flex; align-items: center; gap: 16px; }
.logo { font-size: 15px; font-weight: 700; letter-spacing: -0.02em; display: flex; align-items: center; gap: 8px; }
.icon { width: 24px; height: 24px; background: var(--accent); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; transition: background .3s; }
.header-right { display: flex; align-items: center; gap: 12px; }
.header-chip {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  padding: 4px 10px; border: 1px solid var(--hairline); border-radius: var(--radius-sm);
  color: var(--text-secondary); background: var(--surface); cursor: pointer;
  transition: all .15s; display: flex; align-items: center; gap: 6px;
}
.header-chip:hover { border-color: var(--accent); color: var(--text); background: var(--surface-hover); }
.header-chip.active { border-color: var(--accent); color: var(--accent); background: rgba(255,99,99,.1); }
.shortcut { font-size: 9px; opacity: 0.5; }
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
</style>
