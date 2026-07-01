<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
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
const savedGridScrollTop = ref(0)
const modifierSelecting = ref(false)
const previewLoadingNext = ref(false)
const previewPendingNext = ref(false)
const gridScrollTop = ref(0)
const gridViewportHeight = ref(0)
const gridViewportWidth = ref(0)
const sweptIds = new Set()
let gridResizeObserver = null

const GRID_MIN_WIDTH = 180
const GRID_GAP = 8
const GRID_PADDING_X = 24
const GRID_OVERSCAN_ROWS = 4

const gridColumnCount = computed(() => {
  const width = Math.max(0, gridViewportWidth.value - GRID_PADDING_X)
  return Math.max(1, Math.floor((width + GRID_GAP) / (GRID_MIN_WIDTH + GRID_GAP)))
})

const virtualItemWidth = computed(() => {
  const width = Math.max(0, gridViewportWidth.value - GRID_PADDING_X)
  return (width - GRID_GAP * (gridColumnCount.value - 1)) / gridColumnCount.value
})

const virtualRowHeight = computed(() => Math.max(120, virtualItemWidth.value * 10 / 16 + GRID_GAP))
const totalVirtualRows = computed(() => Math.ceil(ss.gridItems.length / gridColumnCount.value))
const totalVirtualHeight = computed(() => totalVirtualRows.value * virtualRowHeight.value)
const virtualStartRow = computed(() => Math.max(0, Math.floor(gridScrollTop.value / virtualRowHeight.value) - GRID_OVERSCAN_ROWS))
const virtualEndRow = computed(() => {
  const visibleRows = Math.ceil((gridViewportHeight.value || 1) / virtualRowHeight.value)
  return Math.min(totalVirtualRows.value, virtualStartRow.value + visibleRows + GRID_OVERSCAN_ROWS * 2)
})
const topSpacerHeight = computed(() => virtualStartRow.value * virtualRowHeight.value)
const bottomSpacerHeight = computed(() => Math.max(0, totalVirtualHeight.value - virtualEndRow.value * virtualRowHeight.value))
const visibleRows = computed(() => {
  const rows = []
  const columns = gridColumnCount.value
  for (let rowIndex = virtualStartRow.value; rowIndex < virtualEndRow.value; rowIndex++) {
    const start = rowIndex * columns
    rows.push({
      rowIndex,
      items: ss.gridItems.slice(start, start + columns),
    })
  }
  return rows
})

const monitorOptions = computed(() => {
  const total = Math.max(agent.monitorTotal || 1, ...ss.gridItems.map(s => Number(s.monitor_total || 1)))
  return Array.from({ length: total }, (_, index) => index)
})

const gridMonitorValue = computed(() =>
  ss.gridQuery.monitor === null || ss.gridQuery.monitor === undefined ? 'all' : String(ss.gridQuery.monitor)
)

const gridMonitorLabel = computed(() =>
  gridMonitorValue.value === 'all' ? '全部屏幕' : `屏${Number(gridMonitorValue.value) + 1}`
)

function updateGridMetrics() {
  const el = scrollEl.value
  if (!el) return
  gridScrollTop.value = el.scrollTop
  gridViewportHeight.value = el.clientHeight
  gridViewportWidth.value = el.clientWidth
}

function observeGridBody() {
  if (!gridResizeObserver || !scrollEl.value) return
  gridResizeObserver.disconnect()
  gridResizeObserver.observe(scrollEl.value)
  updateGridMetrics()
}

function close() {
  previewItem.value = null
  previewZoom.value = 1
  ss.gridMode = false
}

// 双击截图 → 打开 overlay
function onDblClick(s) {
  savedGridScrollTop.value = scrollEl.value?.scrollTop || 0
  previewItem.value = s
  previewZoom.value = 1
}

function closePreview() {
  const targetId = previewItem.value?.id
  previewItem.value = null
  previewZoom.value = 1
  nextTick(() => {
    observeGridBody()
    if (targetId) scrollToGridItem(targetId, 'center')
    else if (scrollEl.value) scrollEl.value.scrollTop = savedGridScrollTop.value
  })
}

function scrollToGridItem(id, block = 'start') {
  const el = scrollEl.value
  if (!el) return
  const index = ss.gridItems.findIndex(item => item.id === id)
  if (index < 0) {
    el.scrollTop = savedGridScrollTop.value
    updateGridMetrics()
    return
  }
  const rowIndex = Math.floor(index / gridColumnCount.value)
  const centeredOffset = block === 'center'
    ? Math.max(0, (gridViewportHeight.value - virtualRowHeight.value) / 2)
    : 0
  el.scrollTop = Math.max(0, rowIndex * virtualRowHeight.value - centeredOffset)
  updateGridMetrics()
}

function stopModifierSelect() {
  modifierSelecting.value = false
  sweptIds.clear()
}

function addSweptItem(id) {
  if (!modifierSelecting.value || sweptIds.has(id) || ss.gridSelected.has(id)) return
  sweptIds.add(id)
  ss.setGridItemSelected(id, true)
}

function isModifierSelect(event) {
  return event.ctrlKey && event.shiftKey
}

function selectWithModifiers(event, id) {
  if (!isModifierSelect(event)) {
    if (modifierSelecting.value) stopModifierSelect()
    return
  }
  if (!modifierSelecting.value) {
    modifierSelecting.value = true
    sweptIds.clear()
  }
  addSweptItem(id)
}

function onModifierKeyUp(event) {
  if (!event.ctrlKey || !event.shiftKey) stopModifierSelect()
}

function onPreviewKeyDown(event) {
  if (!ss.gridMode || !previewItem.value || event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation?.()
  closePreview()
}

function previewPrev() {
  const idx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (idx > 0) previewItem.value = ss.gridItems[idx - 1]
}

async function changeGridMonitor(event) {
  const value = event.target.value
  const monitor = value === 'all' ? null : Number(value)
  const { dateFrom, dateTo } = ss.gridQuery
  closePreview()
  ss.setGridQuery({ monitor, dateFrom, dateTo })
  ss.resetGrid()
  await ss.loadGrid(false)
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = 0
    updateGridMetrics()
  })
}

function waitForGridIdle() {
  if (!ss.gridLoading) return Promise.resolve()
  return new Promise(resolve => {
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      if (!ss.gridLoading || Date.now() - startedAt > 10000) {
        window.clearInterval(timer)
        resolve()
      }
    }, 50)
  })
}

async function advancePreviewNext() {
  const idx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (idx < 0) return false
  if (idx < ss.gridItems.length - 1) {
    previewItem.value = ss.gridItems[idx + 1]
    return true
  }
  if (ss.gridExhausted) return false

  await waitForGridIdle()
  const currentIdx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (currentIdx < 0) return false
  if (currentIdx < ss.gridItems.length - 1) {
    previewItem.value = ss.gridItems[currentIdx + 1]
    return true
  }
  if (ss.gridExhausted) return false

  const nextIndex = ss.gridItems.length
  await ss.loadGrid(true)
  if (ss.gridItems.length > nextIndex) {
    previewItem.value = ss.gridItems[nextIndex]
    return true
  }
  return false
}

async function previewNext() {
  previewPendingNext.value = true
  if (previewLoadingNext.value) return

  previewLoadingNext.value = true
  try {
    while (previewPendingNext.value) {
      previewPendingNext.value = false
      const advanced = await advancePreviewNext()
      if (!advanced) break
    }
  } finally {
    previewLoadingNext.value = false
  }
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
  if (v && agent.selectedAgent && !ss.gridItems.length && !ss.gridQuery.dateFrom && !ss.gridQuery.dateTo) {
    // 没有预加载数据时才重新加载
    closePreview()
    ss.resetGrid()
    ss.loadGrid(false)
  }
  if (!v) {
    closePreview()
    // 关闭网格时清除预加载数据，下次打开重新加载
    ss.resetGrid({ resetQuery: true })
  }
  nextTick(observeGridBody)
})

watch(() => ss.gridItems.length, () => nextTick(updateGridMetrics))

onMounted(() => {
  window.addEventListener('keyup', onModifierKeyUp)
  window.addEventListener('blur', stopModifierSelect)
  document.addEventListener('keydown', onPreviewKeyDown, true)
  gridResizeObserver = new ResizeObserver(updateGridMetrics)
  nextTick(() => {
    observeGridBody()
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('keyup', onModifierKeyUp)
  window.removeEventListener('blur', stopModifierSelect)
  document.removeEventListener('keydown', onPreviewKeyDown, true)
  gridResizeObserver?.disconnect()
  stopModifierSelect()
})

function onScroll(e) {
  const el = e.target
  updateGridMetrics()
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
    ss.removeGridItems([id])
    ss.notifyScreenshotsChanged()
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
  const index = ss.gridItems.findIndex(s => (s.timestamp || '').substring(0, 10) === date)
  if (index < 0) return
  const rowIndex = Math.floor(index / gridColumnCount.value)
  el.scrollTo({ top: rowIndex * virtualRowHeight.value, behavior: 'smooth' })
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
          <label class="monitor-filter" title="筛选网格截图屏幕">
            <span>{{ gridMonitorLabel }}</span>
            <select :value="gridMonitorValue" @change="changeGridMonitor">
              <option value="all">全部屏幕</option>
              <option v-for="idx in monitorOptions" :key="idx" :value="String(idx)">屏{{ idx + 1 }}</option>
            </select>
          </label>
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
        <div class="grid-virtual">
          <div :style="{ height: `${topSpacerHeight}px` }"></div>
          <div
            v-for="row in visibleRows"
            :key="row.rowIndex"
            class="grid-container"
            :class="{ brushing: modifierSelecting }">
            <div v-for="s in row.items" :key="s.id"
              class="grid-item" :class="{ selected: ss.gridSelected.has(s.id) }"
              :data-grid-id="s.id"
              @pointerenter="selectWithModifiers($event, s.id)"
              @pointermove="selectWithModifiers($event, s.id)"
              @dblclick="onDblClick(s)">
              <input type="checkbox" class="grid-check"
                :checked="ss.gridSelected.has(s.id)" @pointerdown.stop @change="ss.toggleGridItem(s.id)">
              <button class="grid-delete" @pointerdown.stop @click.stop="deleteOne(s.id)">×</button>
              <img :src="getScreenshotImage(s.id)" loading="lazy" draggable="false">
              <div class="grid-time">{{ (s.timestamp||'').replace('T',' ').substring(11,19) }}</div>
              <div class="grid-monitor" v-if="s.monitor_total > 1">屏{{ (s.monitor_index||0)+1 }}</div>
            </div>
          </div>
          <div :style="{ height: `${bottomSpacerHeight}px` }"></div>
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
  flex-wrap: wrap; gap: 8px;
}
.grid-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.grid-count { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.monitor-filter {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  color: var(--text-secondary);
  background: rgba(255,255,255,.04);
  font-family: var(--font-mono);
  font-size: 10px;
  cursor: pointer;
}
.monitor-filter:hover { border-color: var(--accent); color: var(--text); }
.monitor-filter select {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
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
.grid-virtual { padding: 4px 12px 12px; }
.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px; padding: 0 0 8px;
}
.grid-container.brushing { cursor: crosshair; user-select: none; }
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
