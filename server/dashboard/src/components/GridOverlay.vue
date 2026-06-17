<script setup>
import { watch } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { useConfirm } from '../composables/useConfirm'
import { getScreenshotImage, deleteScreenshots } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const { confirm } = useConfirm()

function close() { ss.gridMode = false }

watch(() => ss.gridMode, (v) => {
  if (v && agent.selectedAgent) {
    ss.resetGrid()
    ss.loadGrid(false)
  }
})

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
  <div class="grid-overlay" :class="{ open: ss.gridMode }" @click.self="close">
    <div class="grid-box">
      <div class="grid-header">
        <span class="grid-title">
          <span class="dot" style="background:var(--blue)"></span>
          网格视图
          <span class="grid-count" v-if="ss.gridOffset">{{ ss.gridOffset }} 张</span>
        </span>
        <div class="grid-actions">
          <label class="select-all" v-if="ss.gridItems.length">
            <input type="checkbox"
              :checked="ss.gridSelected.size === ss.gridItems.length && ss.gridItems.length > 0"
              @change="ss.selectAllGrid()">
            全选
          </label>
          <button v-if="ss.gridSelected.size" class="delete-btn" @click="deleteSelected">
            删除选中 ({{ ss.gridSelected.size }})
          </button>
          <button class="close-btn" @click="close">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
            关闭
          </button>
        </div>
      </div>
      <div class="grid-body" @scroll="onScroll">
        <div class="grid-container">
          <div v-for="s in ss.gridItems" :key="s.id"
            class="grid-item" :class="{ selected: ss.gridSelected.has(s.id) }">
            <input type="checkbox" class="grid-check"
              :checked="ss.gridSelected.has(s.id)" @change="ss.toggleGridItem(s.id)">
            <button class="grid-delete" @click.stop="deleteOne(s.id)">×</button>
            <img :src="getScreenshotImage(s.id)" loading="lazy">
            <div class="grid-time">{{ (s.timestamp||'').replace('T',' ').substring(0,16) }}</div>
          </div>
        </div>
        <div class="grid-status" v-if="ss.gridExhausted">已加载 {{ ss.gridOffset }} 张截图</div>
        <div class="grid-status" v-else-if="ss.gridLoading">加载中...</div>
        <div class="grid-status" v-else-if="!ss.gridItems.length && !ss.gridLoading">暂无截图</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid-overlay {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(8px);
  opacity: 0; pointer-events: none; transition: opacity .25s cubic-bezier(0.22,1,0.36,1);
}
.grid-overlay.open { opacity: 1; pointer-events: auto; }
.grid-box {
  width: 80vw; height: 75vh; background: var(--ground);
  border: 1px solid var(--hairline); border-radius: var(--radius-lg);
  overflow: hidden; display: flex; flex-direction: column;
  box-shadow: 0 32px 80px rgba(0,0,0,0.6);
  transform: scale(0.92); transition: transform .3s cubic-bezier(0.22,1,0.36,1);
}
.grid-overlay.open .grid-box { transform: scale(1); }
.grid-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--hairline); flex-shrink: 0;
}
.grid-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.grid-count { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.grid-actions { display: flex; align-items: center; gap: 10px; }
.select-all { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.select-all input { accent-color: var(--accent); width: 14px; height: 14px; }
.delete-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid rgba(242,54,69,.3); border-radius: 6px;
  background: rgba(242,54,69,.08); color: var(--red); cursor: pointer; transition: all .15s;
}
.delete-btn:hover { background: rgba(242,54,69,.15); border-color: var(--red); }
.close-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 4px;
}
.close-btn:hover { border-color: var(--red); color: var(--red); }
.grid-body { flex: 1; overflow-y: auto; min-height: 0; }
.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px; padding: 12px;
}
.grid-item {
  position: relative; border-radius: 6px; overflow: hidden;
  border: 2px solid transparent; cursor: pointer; transition: border-color .15s, transform .15s;
  background: rgba(0,0,0,0.4); aspect-ratio: 16 / 10; min-width: 0;
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
.grid-status { text-align: center; padding: 16px; font-size: 11px; color: var(--muted); }
</style>
