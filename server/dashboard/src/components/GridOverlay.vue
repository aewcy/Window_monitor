<script setup>
import { ref, computed, watch } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { useConfirm } from '../composables/useConfirm'
import { getScreenshotImage, deleteScreenshots } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const { confirm } = useConfirm()
const scrollEl = ref(null)
const previewItem = ref(null)
const previewZoom = ref(1)

function close() {
  previewItem.value = null
  previewZoom.value = 1
  ss.gridMode = false
}

// 双击截图 → 打开 overlay
function onDblClick(s) {
  previewItem.value = s
  previewZoom.value = 1
}

function closePreview() {
  previewItem.value = null
  previewZoom.value = 1
}

function previewPrev() {
  const idx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (idx > 0) previewItem.value = ss.gridItems[idx - 1]
}

function previewNext() {
  const idx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (idx >= 0 && idx < ss.gridItems.length - 1) previewItem.value = ss.gridItems[idx + 1]
}

function onPreviewWheel(e) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    previewZoom.value = Math.min(3, Math.max(0.3, previewZoom.value + delta))
    return
  }
  if (e.deltaY > 0) previewNext()
  else if (e.deltaY < 0) previewPrev()
}

watch(() => ss.gridMode, (v) => {
  if (v && agent.selectedAgent && !ss.gridItems.length) {
    // 没有预加载数据时才重新加载
    closePreview()
    ss.resetGrid()
    ss.loadGrid(false)
  }
  if (!v) {
    closePreview()
    // 关闭网格时清除预加载数据，下次打开重新加载
    ss.resetGrid()
  }
})

function onScroll(e) {
  const el = e.target
  if (ss.gridLoading || ss.gridExhausted) return
  // 距底部 200px 时预加载，确保滚轮滚动流畅
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
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
    if (previewItem.value?.id === id) closePreview()
    ss.loadGrid(false)
  }
}

// 按日期分组
const grouped = computed(() => {
  const map = new Map()
  for (const s of ss.gridItems) {
    const date = (s.timestamp || '').substring(0, 10)
    if (!map.has(date)) map.set(date, [])
    map.get(date).push(s)
  }
  return [...map.entries()].map(([date, items]) => ({ date, items }))
})

// 跳转到指定日期
function scrollTo(date) {
  const el = scrollEl.value
  if (!el) return
  const target = el.querySelector(`[data-date="${date}"]`)
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
          <div class="date-nav" v-if="grouped.length > 1">
            <button v-for="g in grouped" :key="g.date" class="date-chip" @click="scrollTo(g.date)">
              {{ g.date.substring(5) }} <span class="date-count">{{ g.items.length }}</span>
            </button>
          </div>
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
      <div v-if="previewItem" class="grid-preview" @wheel.prevent="onPreviewWheel">
        <div class="preview-toolbar">
          <span class="preview-title">{{ (previewItem.timestamp||'').replace('T',' ') }}</span>
          <div class="preview-actions">
            <span class="zoom-label" v-if="previewZoom !== 1">{{ Math.round(previewZoom * 100) }}%</span>
            <button class="preview-btn" @click="previewPrev">上一张</button>
            <button class="preview-btn" @click="previewNext">下一张</button>
            <button class="preview-btn" @click="closePreview">返回网格</button>
          </div>
        </div>
        <div class="preview-stage">
          <img :src="getScreenshotImage(previewItem.id)" :style="{ transform: `scale(${previewZoom})` }">
        </div>
      </div>
      <div v-else class="grid-body" @scroll="onScroll" ref="scrollEl">
        <template v-for="g in grouped" :key="g.date">
          <div class="grid-date-label" :data-date="g.date">
            <span class="date-text">{{ g.date }}</span>
            <span class="date-total">{{ g.items.length }} 张</span>
          </div>
          <div class="grid-container">
            <div v-for="s in g.items" :key="s.id"
              class="grid-item" :class="{ selected: ss.gridSelected.has(s.id) }"
              @dblclick="onDblClick(s)">
              <input type="checkbox" class="grid-check"
                :checked="ss.gridSelected.has(s.id)" @change="ss.toggleGridItem(s.id)">
              <button class="grid-delete" @click.stop="deleteOne(s.id)">×</button>
              <img :src="getScreenshotImage(s.id)" loading="lazy">
              <div class="grid-time">{{ (s.timestamp||'').replace('T',' ').substring(11,19) }}</div>
              <div class="grid-monitor" v-if="s.monitor_total > 1">屏{{ (s.monitor_index||0)+1 }}</div>
            </div>
          </div>
        </template>
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
  flex-wrap: wrap; gap: 8px;
}
.grid-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.grid-count { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.grid-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.date-nav { display: flex; gap: 4px; }
.date-chip {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 8px; border: 1px solid var(--hairline); border-radius: 12px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
}
.date-chip:hover { border-color: var(--accent); color: var(--accent); }
.date-count { color: var(--muted); }
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
.grid-preview { flex: 1; min-height: 0; display: flex; flex-direction: column; background: rgba(0,0,0,.35); }
.preview-toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 8px 12px; border-bottom: 1px solid var(--hairline); background: var(--surface);
}
.preview-title { font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.zoom-label {
  font-family: var(--font-mono); font-size: 10px; color: var(--amber);
  padding: 2px 8px; background: rgba(251,191,36,.1); border-radius: 4px;
}
.preview-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
}
.preview-btn:hover { background: var(--surface-hover); color: var(--text); }
.preview-stage { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.preview-stage img { max-width: 100%; max-height: 100%; object-fit: contain; transform-origin: center center; transition: transform .15s; }
.grid-date-label {
  display: flex; align-items: center; gap: 8px; padding: 12px 12px 4px;
  position: sticky; top: 0; z-index: 2; background: var(--ground);
}
.date-text { font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--accent); }
.date-total { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px; padding: 4px 12px 12px;
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
  position: absolute; bottom: 0; left: 0;
  background: rgba(0,0,0,0.7);
  color: #fff; font-family: var(--font-mono); font-size: 9px;
  padding: 2px 6px; pointer-events: none; border-radius: 0 4px 0 0;
}
.grid-monitor {
  position: absolute; bottom: 0; right: 0;
  background: rgba(0,0,0,0.7);
  color: var(--blue); font-family: var(--font-mono); font-size: 9px;
  padding: 2px 6px; pointer-events: none; border-radius: 4px 0 0 0;
}
.grid-status { text-align: center; padding: 16px; font-size: 11px; color: var(--muted); }
</style>
