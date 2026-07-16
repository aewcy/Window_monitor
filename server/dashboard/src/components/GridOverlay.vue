<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { useConfirm } from '../composables/useConfirm'
import { getScreenshotImage, getScreenshotThumb, getScreenshotThumbsBatch, deleteScreenshots, getAppEvents } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const { confirm } = useConfirm()
const scrollEl = ref(null)
const previewStageEl = ref(null)
const previewItem = ref(null)
const previewZoom = ref(1)
const previewPanX = ref(0)
const previewPanY = ref(0)
const previewDragging = ref(false)
const savedGridScrollTop = ref(0)
const modifierSelecting = ref(false)
const previewLoadingNext = ref(false)
const previewPendingNext = ref(false)
const previewMetaOpen = ref(false)
const previewCopiedKey = ref('')
const gridView = ref('screenshots')
const activityEl = ref(null)
const activityEvents = ref([])
const activityLoading = ref(false)
const activityLoadedKey = ref('')
const anchorTimestamp = ref(null)
const thumbDataUrls = ref(new Map())
const gridScrollTop = ref(0)
const gridViewportHeight = ref(0)
const gridViewportWidth = ref(0)
const sweptIds = new Set()
let gridResizeObserver = null
let previewDragStart = null
let gridClickTimer = null

const GRID_MIN_WIDTH = 180
const GRID_GAP = 8
const GRID_PADDING_X = 24
const GRID_OVERSCAN_ROWS = 4
const PREVIEW_PRELOAD_RADIUS = 3
const ACTIVITY_LIMIT = 5000
const ACTIVITY_ROW_HEIGHT = 30
const THUMB_BATCH_SIZE = 250
const THUMB_BATCH_CONCURRENCY = 3
const preloadedPreviewImages = new Set()
const preloadedThumbImages = new Set()
const thumbPrefetchQueued = new Set()
let thumbPrefetchQueue = []
let activeThumbBatchLoads = 0
let thumbPrefetchGeneration = 0

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
const activeStartRow = computed(() => Math.max(0, Math.floor(gridScrollTop.value / virtualRowHeight.value)))
const activeEndRow = computed(() => {
  const visibleRows = Math.ceil((gridViewportHeight.value || 1) / virtualRowHeight.value)
  return Math.min(totalVirtualRows.value, activeStartRow.value + visibleRows + 1)
})
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

const activityRange = computed(() => {
  const { dateFrom, dateTo } = ss.gridQuery
  if (dateFrom && dateTo) return { dateFrom, dateTo }
  if (!ss.gridItems.length) return { dateFrom: null, dateTo: null }
  const times = ss.gridItems.map(item => item.timestamp).filter(Boolean).sort()
  return { dateFrom: times[0], dateTo: times[times.length - 1] }
})

const activityRangeKey = computed(() =>
  [
    agent.selectedAgent || '',
    gridMonitorValue.value,
    activityRange.value.dateFrom || '',
    activityRange.value.dateTo || '',
  ].join('|')
)

function updateGridMetrics() {
  const el = scrollEl.value
  if (!el) return
  gridScrollTop.value = el.scrollTop
  gridViewportHeight.value = el.clientHeight
  gridViewportWidth.value = el.clientWidth
  updateGridAnchor()
}

function observeGridBody() {
  if (!gridResizeObserver || !scrollEl.value) return
  gridResizeObserver.disconnect()
  gridResizeObserver.observe(scrollEl.value)
  updateGridMetrics()
}

function close() {
  previewItem.value = null
  resetPreviewTransform()
  resetThumbPrefetchQueue()
  gridView.value = 'screenshots'
  ss.gridMode = false
}

function resetPreviewTransform() {
  previewZoom.value = 1
  previewPanX.value = 0
  previewPanY.value = 0
  previewDragging.value = false
  previewDragStart = null
}

const previewMetaRows = computed(() => {
  const item = previewItem.value || {}
  const rows = [
    ['网址', item.foreground_url || item.url || ''],
    ['程序', item.foreground_process_name || item.process_name || ''],
    ['标题', item.foreground_window_title || item.window_title || item.title || ''],
    ['规则', item.matched_rule_type ? `${item.matched_rule_type}: ${item.matched_rule_pattern || ''}` : ''],
    ['策略', item.save_policy_phase || ''],
    ['被控机', item.agent_name || agent.selectedAgent || ''],
    ['屏幕', item.monitor_total > 1 ? `屏${Number(item.monitor_index || 0) + 1}/${item.monitor_total}` : ''],
    ['时间', (item.timestamp || item.screenshot_time || '').replace('T', ' ')],
  ]
  return rows.filter(([, value]) => String(value || '').trim())
})

const previewPrimaryUrl = computed(() => {
  const item = previewItem.value || {}
  return item.foreground_url || item.url || ''
})

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {}
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(textarea)
  return ok
}

async function copyPreviewValue(value, key = 'value') {
  const text = String(value || '').trim()
  if (!text) return
  const ok = await copyTextToClipboard(text)
  previewCopiedKey.value = ok ? key : `failed:${key}`
  window.setTimeout(() => {
    if (previewCopiedKey.value === key || previewCopiedKey.value === `failed:${key}`) {
      previewCopiedKey.value = ''
    }
  }, 1400)
}

function isActiveViewportRow(rowIndex) {
  return rowIndex >= activeStartRow.value && rowIndex < activeEndRow.value
}

function gridImagePriority(rowIndex) {
  return isActiveViewportRow(rowIndex) ? 'high' : 'low'
}

function preloadScreenshot(id) {
  if (!id || preloadedPreviewImages.has(id)) return
  preloadedPreviewImages.add(id)
  const img = new Image()
  img.fetchPriority = 'high'
  img.decoding = 'async'
  img.src = getScreenshotImage(id)
}

function screenshotThumbSrc(item) {
  return thumbDataUrls.value.get(item?.id) || item?.thumb_url || getScreenshotThumb(item?.id)
}

function resetThumbPrefetchQueue() {
  thumbPrefetchGeneration += 1
  thumbPrefetchQueue = []
  thumbPrefetchQueued.clear()
  activeThumbBatchLoads = 0
  preloadedThumbImages.clear()
  thumbDataUrls.value = new Map()
}

function queueThumbnailPrefetch(item, highPriority = false) {
  const id = item?.id
  if (!id || preloadedThumbImages.has(id)) return
  if (thumbPrefetchQueued.has(id)) {
    if (highPriority) {
      thumbPrefetchQueue = thumbPrefetchQueue.filter(queuedItem => queuedItem?.id !== id)
      thumbPrefetchQueue.unshift(item)
    }
    return
  }
  thumbPrefetchQueued.add(id)
  if (highPriority) thumbPrefetchQueue.unshift(item)
  else thumbPrefetchQueue.push(item)
  runThumbnailPrefetchQueue()
}

function runThumbnailPrefetchQueue() {
  while (activeThumbBatchLoads < THUMB_BATCH_CONCURRENCY && thumbPrefetchQueue.length) {
    const batch = []
    while (batch.length < THUMB_BATCH_SIZE && thumbPrefetchQueue.length) {
      const item = thumbPrefetchQueue.shift()
      const id = item?.id
      if (!id || preloadedThumbImages.has(id)) continue
      batch.push(item)
    }
    if (!batch.length) continue
    const generation = thumbPrefetchGeneration
    activeThumbBatchLoads += 1
    getScreenshotThumbsBatch(batch.map(item => item.id))
      .then(data => {
        if (generation !== thumbPrefetchGeneration) return
        const next = new Map(thumbDataUrls.value)
        for (const thumb of data.thumbs || []) {
          preloadedThumbImages.add(thumb.id)
          next.set(thumb.id, `data:image/jpeg;base64,${thumb.image_base64}`)
        }
        thumbDataUrls.value = next
      })
      .catch(() => {})
      .finally(() => {
        activeThumbBatchLoads = Math.max(0, activeThumbBatchLoads - 1)
        if (generation === thumbPrefetchGeneration) runThumbnailPrefetchQueue()
      })
  }
}

function prefetchVisibleThumbnails() {
  for (const row of visibleRows.value) {
    const highPriority = isActiveViewportRow(row.rowIndex)
    for (const item of row.items) queueThumbnailPrefetch(item, highPriority)
  }
}

function prefetchAllThumbnails() {
  prefetchVisibleThumbnails()
  for (const item of ss.gridItems) queueThumbnailPrefetch(item, false)
}

function preloadPreviewNeighbors() {
  const idx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (idx < 0) return
  preloadScreenshot(previewItem.value.id)
  for (let offset = 1; offset <= PREVIEW_PRELOAD_RADIUS; offset++) {
    preloadScreenshot(ss.gridItems[idx - offset]?.id)
    preloadScreenshot(ss.gridItems[idx + offset]?.id)
  }
}

function clearGridClickTimer() {
  if (!gridClickTimer) return
  window.clearTimeout(gridClickTimer)
  gridClickTimer = null
}

function onGridItemClick(event, id) {
  if (event.button !== 0 || event.defaultPrevented) return
  if (isModifierSelect(event)) return
  if (event.target?.closest?.('.grid-check, .grid-delete')) return
  clearGridClickTimer()
  gridClickTimer = window.setTimeout(() => {
    ss.toggleGridItem(id)
    gridClickTimer = null
  }, 160)
}

// 双击截图 → 打开 overlay
function onDblClick(s) {
  clearGridClickTimer()
  savedGridScrollTop.value = scrollEl.value?.scrollTop || 0
  previewItem.value = s
  previewMetaOpen.value = false
  resetPreviewTransform()
  preloadPreviewNeighbors()
}

function togglePreviewSelection() {
  if (!previewItem.value?.id) return
  ss.toggleGridItem(previewItem.value.id)
}

function selectOnlyPreviewItem() {
  if (!previewItem.value?.id) return
  ss.selectOnlyGridItem(previewItem.value.id)
}

function closePreview() {
  const targetId = previewItem.value?.id
  previewItem.value = null
  previewMetaOpen.value = false
  resetPreviewTransform()
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

function updateGridAnchor() {
  if (!ss.gridItems.length || gridView.value !== 'screenshots') return
  const centerRow = Math.max(0, Math.floor((gridScrollTop.value + gridViewportHeight.value / 2) / virtualRowHeight.value))
  const centerIndex = Math.min(ss.gridItems.length - 1, centerRow * gridColumnCount.value + Math.floor(gridColumnCount.value / 2))
  anchorTimestamp.value = ss.gridItems[centerIndex]?.timestamp || anchorTimestamp.value
}

function timeDistance(a, b) {
  if (!a || !b) return Number.MAX_SAFE_INTEGER
  return Math.abs(new Date(a).getTime() - new Date(b).getTime())
}

function findNearestScreenshotIndex(timestamp) {
  if (!timestamp) return -1
  let bestIndex = -1
  let bestDistance = Number.MAX_SAFE_INTEGER
  ss.gridItems.forEach((item, index) => {
    const distance = timeDistance(item.timestamp, timestamp)
    if (distance < bestDistance) {
      bestIndex = index
      bestDistance = distance
    }
  })
  return bestIndex
}

function scrollToGridTime(timestamp) {
  const el = scrollEl.value
  if (!el || !timestamp) return
  const index = findNearestScreenshotIndex(timestamp)
  if (index < 0) return
  const rowIndex = Math.floor(index / gridColumnCount.value)
  el.scrollTop = Math.max(0, rowIndex * virtualRowHeight.value - Math.max(0, (gridViewportHeight.value - virtualRowHeight.value) / 2))
  updateGridMetrics()
}

function findNearestActivityIndex(timestamp) {
  if (!timestamp) return -1
  let bestIndex = -1
  let bestDistance = Number.MAX_SAFE_INTEGER
  activityEvents.value.forEach((item, index) => {
    const distance = timeDistance(item.timestamp, timestamp)
    if (distance < bestDistance) {
      bestIndex = index
      bestDistance = distance
    }
  })
  return bestIndex
}

function scrollToActivityTime(timestamp) {
  const el = activityEl.value
  if (!el || !activityEvents.value.length || !timestamp) return
  const index = findNearestActivityIndex(timestamp)
  if (index < 0) return
  el.scrollTop = Math.max(0, index * ACTIVITY_ROW_HEIGHT - el.clientHeight / 2)
}

async function loadActivityEvents(force = false) {
  if (!agent.selectedAgent) return
  if (!force && activityLoadedKey.value === activityRangeKey.value) return
  activityLoading.value = true
  try {
    const { dateFrom, dateTo } = activityRange.value
    activityEvents.value = await getAppEvents(
      agent.selectedAgent,
      ACTIVITY_LIMIT,
      0,
      ss.gridQuery.monitor,
      dateFrom,
      dateTo,
    )
    activityLoadedKey.value = activityRangeKey.value
  } catch {
    activityEvents.value = []
  } finally {
    activityLoading.value = false
  }
}

async function switchGridView(view) {
  if (gridView.value === view) return
  if (previewItem.value) closePreview()
  if (gridView.value === 'screenshots') updateGridAnchor()
  else updateActivityAnchor()

  gridView.value = view
  if (view === 'activity') {
    await loadActivityEvents()
    nextTick(() => scrollToActivityTime(anchorTimestamp.value))
    return
  }
  nextTick(() => scrollToGridTime(anchorTimestamp.value))
}

function updateActivityAnchor() {
  const el = activityEl.value
  if (!el || !activityEvents.value.length || gridView.value !== 'activity') return
  const index = Math.min(activityEvents.value.length - 1, Math.max(0, Math.floor((el.scrollTop + el.clientHeight / 2) / ACTIVITY_ROW_HEIGHT)))
  anchorTimestamp.value = activityEvents.value[index]?.timestamp || anchorTimestamp.value
}

function onActivityScroll() {
  updateActivityAnchor()
}

function onActivityClick(event) {
  anchorTimestamp.value = event.screenshot_time || event.timestamp
  if (event.screenshot_id) {
    const existingItem = ss.gridItems.find(item => item.id === event.screenshot_id)
    previewItem.value = existingItem || {
      id: event.screenshot_id,
      timestamp: event.screenshot_time || event.timestamp,
      foreground_process_name: event.process_name || '',
      foreground_window_title: event.window_title || '',
      monitor_total: agent.monitorTotal || 1,
      monitor_index: ss.gridQuery.monitor ?? 0,
    }
    previewMetaOpen.value = false
    resetPreviewTransform()
    preloadPreviewNeighbors()
    return
  }

  gridView.value = 'screenshots'
  nextTick(() => scrollToGridTime(anchorTimestamp.value))
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
  if (idx > 0) {
    previewItem.value = ss.gridItems[idx - 1]
    resetPreviewTransform()
    preloadPreviewNeighbors()
  }
}

async function changeGridMonitor(event) {
  const value = event.target.value
  const monitor = value === 'all' ? null : Number(value)
  const { dateFrom, dateTo } = ss.gridQuery
  closePreview()
  gridView.value = 'screenshots'
  activityLoadedKey.value = ''
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
    resetPreviewTransform()
    preloadPreviewNeighbors()
    return true
  }
  if (ss.gridExhausted) return false

  await waitForGridIdle()
  const currentIdx = ss.gridItems.findIndex(s => s.id === previewItem.value?.id)
  if (currentIdx < 0) return false
  if (currentIdx < ss.gridItems.length - 1) {
    previewItem.value = ss.gridItems[currentIdx + 1]
    resetPreviewTransform()
    preloadPreviewNeighbors()
    return true
  }
  if (ss.gridExhausted) return false

  const nextIndex = ss.gridItems.length
  await ss.loadGrid(true)
  if (ss.gridItems.length > nextIndex) {
    previewItem.value = ss.gridItems[nextIndex]
    resetPreviewTransform()
    preloadPreviewNeighbors()
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
    const oldZoom = previewZoom.value
    const nextZoom = Math.min(3, Math.max(0.3, oldZoom + (e.deltaY > 0 ? -0.1 : 0.1)))
    if (nextZoom === oldZoom) return

    const rect = previewStageEl.value?.getBoundingClientRect()
    if (rect) {
      const pointerX = e.clientX - rect.left - rect.width / 2
      const pointerY = e.clientY - rect.top - rect.height / 2
      previewPanX.value = pointerX - ((pointerX - previewPanX.value) / oldZoom) * nextZoom
      previewPanY.value = pointerY - ((pointerY - previewPanY.value) / oldZoom) * nextZoom
    }
    previewZoom.value = nextZoom
    return
  }
  if (e.deltaY > 0) previewNext()
  else if (e.deltaY < 0) previewPrev()
}

function onPreviewPointerDown(e) {
  if (e.button !== 0) return
  e.preventDefault()
  previewDragging.value = true
  previewDragStart = {
    pointerId: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    panX: previewPanX.value,
    panY: previewPanY.value,
  }
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onPreviewPointerMove(e) {
  if (!previewDragging.value || !previewDragStart) return
  e.preventDefault()
  previewPanX.value = previewDragStart.panX + e.clientX - previewDragStart.x
  previewPanY.value = previewDragStart.panY + e.clientY - previewDragStart.y
}

function stopPreviewDrag(e) {
  if (previewDragStart && e?.pointerId === previewDragStart.pointerId) {
    e.currentTarget?.releasePointerCapture?.(e.pointerId)
  }
  previewDragging.value = false
  previewDragStart = null
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
    gridView.value = 'screenshots'
    activityEvents.value = []
    activityLoadedKey.value = ''
    resetThumbPrefetchQueue()
    // 关闭网格时清除预加载数据，下次打开重新加载
    ss.resetGrid({ resetQuery: true })
  }
  nextTick(observeGridBody)
})

watch(() => ss.gridItems.length, () => {
  activityLoadedKey.value = ''
  nextTick(() => {
    updateGridMetrics()
    prefetchAllThumbnails()
  })
})
watch(() => previewItem.value?.id, () => preloadPreviewNeighbors())

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
  clearGridClickTimer()
  stopModifierSelect()
  stopPreviewDrag()
})

function onScroll(e) {
  const el = e.target
  updateGridMetrics()
  prefetchVisibleThumbnails()
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
          <span class="view-tabs">
            <button class="view-tab" :class="{ active: gridView === 'screenshots' }" @click="switchGridView('screenshots')">截图</button>
            <button class="view-tab" :class="{ active: gridView === 'activity' }" @click="switchGridView('activity')">活动</button>
          </span>
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
            <button
              class="preview-btn select-current"
              :class="{ active: ss.gridSelected.has(previewItem.id) }"
              @click="togglePreviewSelection">
              {{ ss.gridSelected.has(previewItem.id) ? '取消选中' : '选中此图' }}
            </button>
            <button class="preview-btn" @click="selectOnlyPreviewItem">只选此图</button>
            <button class="preview-btn" @click="previewPrev">上一张</button>
            <button class="preview-btn" @click="previewNext">下一张</button>
            <button class="preview-btn" @click="closePreview">返回网格</button>
          </div>
        </div>
        <div class="preview-stage"
          ref="previewStageEl"
          :class="{ dragging: previewDragging }"
          @pointerdown="onPreviewPointerDown"
          @pointermove="onPreviewPointerMove"
          @pointerup="stopPreviewDrag"
          @pointercancel="stopPreviewDrag">
          <img
            :src="getScreenshotImage(previewItem.id)"
            fetchpriority="high"
            loading="eager"
            decoding="async"
            draggable="false"
            :style="{ transform: `translate(${previewPanX}px, ${previewPanY}px) scale(${previewZoom})` }">
          <div
            class="image-meta"
            v-if="previewMetaRows.length"
            @pointerdown.stop
            @pointermove.stop
            @pointerup.stop
            @pointercancel.stop
            @wheel.stop
            @click.stop>
            <button
              class="meta-corner"
              :class="{ open: previewMetaOpen }"
              title="查看图片网址和程序信息"
              @click="previewMetaOpen = !previewMetaOpen">
              <span></span>
            </button>
            <div class="meta-panel" v-if="previewMetaOpen">
              <div class="meta-head">
                <span>图片信息</span>
                <button v-if="previewPrimaryUrl" class="copy-url" @click="copyPreviewValue(previewPrimaryUrl, 'url')">
                  {{ previewCopiedKey === 'url' ? '已复制' : previewCopiedKey === 'failed:url' ? '复制失败' : '复制 URL' }}
                </button>
              </div>
              <div class="meta-row" v-for="[label, value] in previewMetaRows" :key="label">
                <span class="meta-label">{{ label }}</span>
                <span class="meta-value" :title="value">{{ value }}</span>
                <button class="copy-field" title="复制此项" @click="copyPreviewValue(value, label)">
                  {{ previewCopiedKey === label ? '已复制' : previewCopiedKey === `failed:${label}` ? '失败' : '复制' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="gridView === 'screenshots'" class="grid-body" @scroll="onScroll" ref="scrollEl">
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
              @click="onGridItemClick($event, s.id)"
              @pointerenter="selectWithModifiers($event, s.id)"
              @pointermove="selectWithModifiers($event, s.id)"
              @dblclick="onDblClick(s)">
              <input type="checkbox" class="grid-check"
                :checked="ss.gridSelected.has(s.id)" @pointerdown.stop @click.stop @change.stop="ss.toggleGridItem(s.id)">
              <button class="grid-delete" @pointerdown.stop @click.stop="deleteOne(s.id)">×</button>
              <img
                :src="screenshotThumbSrc(s)"
                :fetchpriority="gridImagePriority(row.rowIndex)"
                loading="eager"
                decoding="async"
                draggable="false">
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
      <div v-else class="activity-body" ref="activityEl" @scroll="onActivityScroll">
        <div class="activity-range">
          <span>{{ (activityRange.dateFrom || '').replace('T', ' ') || '当前已加载范围' }}</span>
          <span>至</span>
          <span>{{ (activityRange.dateTo || '').replace('T', ' ') || '最新' }}</span>
        </div>
        <div v-for="e in activityEvents" :key="e.id"
          class="activity-row" :class="{ clickable: e.screenshot_id }"
          @click="onActivityClick(e)">
          <span class="activity-time">{{ (e.timestamp||'').replace('T',' ').substring(11,19) }}</span>
          <span class="activity-badge" :class="e.event_type === 'chat' ? 'chat' : 'window'">
            {{ e.event_type === 'chat' ? '聊天' : '窗口' }}
          </span>
          <span class="activity-app">{{ e.process_name }}</span>
          <span class="activity-title">{{ e.window_title }}</span>
        </div>
        <div class="grid-status" v-if="activityLoading">加载活动记录...</div>
        <div class="grid-status" v-else-if="!activityEvents.length">当前时间范围暂无活动记录</div>
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
.view-tabs {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--hairline);
  border-radius: 7px;
  background: rgba(0,0,0,.18);
}
.view-tab {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  min-width: 42px; height: 22px; padding: 0 10px;
  border: 0; border-radius: 5px;
  color: var(--text-secondary); background: transparent; cursor: pointer;
}
.view-tab:hover { color: var(--text); }
.view-tab.active { color: #fff; background: rgba(96,165,250,.28); }
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
.activity-body { flex: 1; overflow-y: auto; min-height: 0; background: rgba(0,0,0,.18); }
.activity-range {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 8px;
  min-height: 30px; padding: 0 16px;
  border-bottom: 1px solid var(--hairline);
  background: var(--ground);
  color: var(--muted); font-family: var(--font-mono); font-size: 10px;
}
.activity-row {
  min-height: 30px; display: grid;
  grid-template-columns: 58px 42px minmax(90px, 140px) minmax(0, 1fr);
  align-items: center; gap: 10px;
  padding: 0 16px; border-bottom: 1px solid rgba(255,255,255,.025);
  font-size: 12px; transition: background .1s;
}
.activity-row:hover { background: rgba(255,255,255,.035); }
.activity-row.clickable { cursor: pointer; }
.activity-row.clickable:hover { background: rgba(96,165,250,.08); }
.activity-time { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.activity-badge {
  font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
  text-align: center;
}
.activity-badge.window { background: rgba(96,165,250,.12); color: var(--blue); }
.activity-badge.chat { background: rgba(167,139,250,.12); color: var(--purple); }
.activity-app {
  color: var(--amber); font-family: var(--font-mono); font-size: 11px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.activity-title { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
.preview-btn.select-current.active {
  border-color: rgba(34,197,94,.45);
  background: rgba(34,197,94,.12);
  color: var(--green);
}
.preview-stage {
  flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; overflow: hidden;
  cursor: grab; user-select: none; touch-action: none;
}
.preview-stage.dragging { cursor: grabbing; }
.preview-stage img {
  max-width: 100%; max-height: 100%; object-fit: contain; transform-origin: center center;
  transition: transform .12s; pointer-events: none;
}
.preview-stage.dragging img { transition: none; }
.image-meta {
  position: absolute; right: 14px; bottom: 14px; z-index: 5;
  display: flex; align-items: flex-end; justify-content: flex-end;
  cursor: default; user-select: text;
}
.meta-corner {
  width: 28px; height: 28px; border: 1px solid rgba(255,255,255,.2);
  border-radius: 8px; background: rgba(0,0,0,.64); color: var(--text-secondary);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(8px); transition: all .15s;
}
.meta-corner:hover, .meta-corner.open { border-color: var(--blue); color: var(--blue); background: rgba(15,23,42,.86); }
.meta-corner span {
  width: 0; height: 0; border-left: 8px solid currentColor; border-top: 8px solid transparent;
  transform: rotate(45deg); transform-origin: center;
}
.meta-panel {
  position: absolute; right: 0; bottom: 36px;
  width: min(460px, calc(80vw - 48px)); max-height: min(42vh, 360px); overflow: auto;
  padding: 12px; border: 1px solid rgba(255,255,255,.14); border-radius: 12px;
  background: rgba(10,14,22,.92); box-shadow: 0 18px 50px rgba(0,0,0,.45);
  backdrop-filter: blur(12px); cursor: default; user-select: text;
}
.meta-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; color: var(--text); font-size: 12px; font-weight: 700; }
.copy-url {
  border: 1px solid var(--hairline); border-radius: 6px; background: rgba(255,255,255,.06);
  color: var(--text-secondary); cursor: pointer; font-family: var(--font-mono); font-size: 10px; padding: 3px 8px;
}
.copy-url:hover { border-color: var(--blue); color: var(--blue); }
.meta-row {
  display: grid; grid-template-columns: 48px minmax(0, 1fr) auto; gap: 10px;
  padding: 6px 0; border-top: 1px solid rgba(255,255,255,.06);
  font-size: 11px; line-height: 1.35;
}
.meta-label { color: var(--muted); font-family: var(--font-mono); }
.meta-value { color: var(--text-secondary); overflow-wrap: anywhere; word-break: break-word; cursor: text; }
.copy-field {
  align-self: start; border: 1px solid transparent; border-radius: 5px; background: transparent;
  color: var(--muted); cursor: pointer; font-family: var(--font-mono); font-size: 9px; padding: 1px 5px;
}
.copy-field:hover { border-color: var(--hairline); color: var(--blue); background: rgba(96,165,250,.08); }
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
