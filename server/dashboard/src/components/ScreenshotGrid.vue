<script setup>
import { watch } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { useConfirm } from '../composables/useConfirm'
import { getScreenshotImage, deleteScreenshots } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const { confirm } = useConfirm()

watch(() => agent.selectedAgent, () => { if (agent.selectedAgent && ss.gridMode) ss.loadGrid(false) })
watch(() => ss.gridMode, (v) => { if (v && agent.selectedAgent) { ss.resetGrid(); ss.loadGrid(false) } })

function onScroll(e) {
  const el = e.target
  if (ss.gridLoading || ss.gridExhausted) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 100) {
    ss.loadGrid(true)
  }
}

async function deleteSelected() {
  if (!ss.gridSelected.size) return
  const ok = await confirm(`删除 ${ss.gridSelected.size} 张截图？此操作不可撤销。`)
  if (ok) await ss.deleteSelected()
}

async function deleteOne(id) {
  const ok = await confirm('删除此截图？')
  if (ok) {
    await deleteScreenshots([id])
    ss.loadGrid(false)
  }
}
</script>

<template>
  <div class="grid-wrapper">
    <div class="grid-toolbar">
      <label class="select-all">
        <input type="checkbox" :checked="ss.gridSelected.size === ss.gridItems.length && ss.gridItems.length > 0" @change="ss.selectAllGrid()">
        全选
      </label>
      <span class="grid-info">{{ ss.gridOffset }} 张</span>
      <button v-if="ss.gridSelected.size" class="delete-btn" @click="deleteSelected">删除选中 ({{ ss.gridSelected.size }})</button>
    </div>
    <div class="grid-container" @scroll="onScroll">
      <div v-for="s in ss.gridItems" :key="s.id"
        class="grid-item" :class="{ selected: ss.gridSelected.has(s.id) }">
        <input type="checkbox" class="grid-check" :checked="ss.gridSelected.has(s.id)" @change="ss.toggleGridItem(s.id)">
        <button class="grid-delete" @click.stop="deleteOne(s.id)">×</button>
        <img :src="getScreenshotImage(s.id)" loading="lazy">
        <div class="grid-time">{{ (s.timestamp||'').replace('T',' ').substring(0,16) }}</div>
      </div>
      <div class="grid-status" v-if="ss.gridExhausted">已加载 {{ ss.gridOffset }} 张截图</div>
      <div class="grid-status" v-else-if="ss.gridLoading">加载中...</div>
      <div class="grid-status" v-else-if="!ss.gridItems.length && !ss.gridLoading">暂无截图</div>
    </div>
  </div>
</template>

<style scoped>
.grid-wrapper { display: flex; flex-direction: column; height: 100%; }
.grid-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; border-bottom: 1px solid var(--hairline); flex-shrink: 0;
}
.select-all { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.select-all input { accent-color: var(--accent); width: 14px; height: 14px; }
.grid-info { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.delete-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 10px; border: 1px solid rgba(242,54,69,.3); border-radius: 6px;
  background: rgba(242,54,69,.08); color: var(--red); cursor: pointer; margin-left: auto; transition: all .15s;
}
.delete-btn:hover { background: rgba(242,54,69,.15); border-color: var(--red); }
.grid-container {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px; padding: 8px; overflow-y: auto; flex: 1; align-content: start;
}
.grid-item {
  position: relative; border-radius: 6px; overflow: hidden;
  border: 2px solid transparent; cursor: pointer; transition: border-color .15s, transform .15s;
  background: rgba(0,0,0,0.4); aspect-ratio: 16/10;
}
.grid-item:hover { border-color: var(--accent); transform: scale(1.02); }
.grid-item.selected { border-color: var(--green); }
.grid-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
.grid-check {
  position: absolute; top: 6px; left: 6px; z-index: 2;
  width: 16px; height: 16px; accent-color: var(--accent); opacity: 0; transition: opacity .15s;
}
.grid-item:hover .grid-check, .grid-item.selected .grid-check { opacity: 1; }
.grid-delete {
  position: absolute; top: 4px; right: 4px; z-index: 2;
  width: 22px; height: 22px; border-radius: 50%; border: none;
  background: rgba(0,0,0,0.6); color: var(--red); font-size: 12px;
  cursor: pointer; display: none; align-items: center; justify-content: center; transition: background .15s;
}
.grid-item:hover .grid-delete { display: flex; }
.grid-delete:hover { background: rgba(242,54,69,.3); }
.grid-time {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,0.8));
  color: #fff; font-family: var(--font-mono); font-size: 9px;
  padding: 16px 6px 4px; pointer-events: none;
}
.grid-status { grid-column: 1/-1; text-align: center; padding: 12px; font-size: 11px; color: var(--muted); }
</style>
