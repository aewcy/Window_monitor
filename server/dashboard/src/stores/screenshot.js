import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'
import { useAgentStore } from './agent'

export const useScreenshotStore = defineStore('screenshot', () => {
  const liveMode = ref(true)
  const gridMode = ref(false)
  const gridItems = ref([])
  const gridSelected = ref(new Set())
  const gridOffset = ref(0)
  const gridLoading = ref(false)
  const gridExhausted = ref(false)
  const gridQuery = ref({ monitor: null, dateFrom: null, dateTo: null })
  const liveOpen = ref(false)
  const liveInterval = ref(null)

  // 浏览模式: 'live' | 'timeline' | 'browser'
  const displaySource = ref('live')
  const displayItems = ref([])  // 带 screenshot_id + title 的条目列表
  const displayIndex = ref(0)

  const BATCH = 200
  const MAX_GRID_PRELOAD = 10000

  const currentDisplayItem = computed(() => displayItems.value[displayIndex.value] || null)
  const livePollMs = computed(() => {
    const agent = useAgentStore()
    const interval = liveInterval.value || agent.selectedAgentData?.screenshot_interval || 1
    return Math.max(250, Math.min(60000, Number(interval) * 1000 || 1000))
  })

  async function loadLatest(options = {}) {
    const agent = useAgentStore()
    const agentName = options.agentName ?? agent.selectedAgent
    const monitor = options.monitor ?? agent.selectedMonitor
    if (!agentName) return null
    const allowStoredFallback = options.allowStoredFallback !== false
    let data
    try {
      data = await api.getLatestLiveScreenshot(agentName, monitor, allowStoredFallback)
    } catch (err) {
      if (!allowStoredFallback) return null
      data = await api.getLatestScreenshot(agentName, monitor)
    }
    if (data && (data.id || data.image_base64)) {
      const stillCurrent = agent.selectedAgent === agentName && agent.selectedMonitor === monitor
      if (stillCurrent) {
        agent.setMonitorTotal(data.monitor_total || 1)
        liveInterval.value = data.capture_interval || agent.selectedAgentData?.screenshot_interval || liveInterval.value
      }
    }
    return data
  }

  function prev() {
    if (displayItems.value.length && displaySource.value !== 'live') {
      if (displayIndex.value > 0) displayIndex.value--
      else displayIndex.value = displayItems.value.length - 1 // 循环
    }
  }

  function next() {
    if (displayItems.value.length && displaySource.value !== 'live') {
      if (displayIndex.value < displayItems.value.length - 1) displayIndex.value++
      else displayIndex.value = 0 // 循环
    }
  }

  // 进入时间线浏览模式
  function browseTimeline(items, startIndex) {
    displaySource.value = 'timeline'
    displayItems.value = items.filter(e => e.screenshot_id)
    displayIndex.value = Math.max(0, displayItems.value.findIndex(e => e === items[startIndex]))
  }

  // 进入浏览器历史浏览模式
  function browseBrowser(items, startIndex) {
    displaySource.value = 'browser'
    displayItems.value = items.filter(r => r.screenshot_id)
    displayIndex.value = Math.max(0, displayItems.value.findIndex(r => r === items[startIndex]))
  }

  // 回到实时模式
  function goLive() {
    displaySource.value = 'live'
    displayItems.value = []
    displayIndex.value = 0
    liveMode.value = true
  }

  function resetLiveInterval(value = null) {
    liveInterval.value = value
  }

  async function loadGrid(append = false, limitOverride = null) {
    const agent = useAgentStore()
    if (!agent.selectedAgent || gridLoading.value || (append && gridExhausted.value)) return 0
    gridLoading.value = true
    try {
      const offset = append ? gridOffset.value : 0
      const query = gridQuery.value
      const limit = Math.max(1, Math.min(MAX_GRID_PRELOAD, Number(limitOverride || BATCH)))
      const data = await api.getScreenshots(
        agent.selectedAgent,
        limit,
        offset,
        query.monitor,
        query.dateFrom,
        query.dateTo,
      )
      if (!append) {
        gridItems.value = []
        gridOffset.value = 0
        gridExhausted.value = false
        gridSelected.value = new Set()
      }
      if (!append && !query.dateTo && data.length) {
        gridQuery.value = { ...gridQuery.value, dateTo: data[0].timestamp }
      }
      const existingIds = new Set(gridItems.value.map(item => item.id))
      const uniqueData = data.filter(item => !existingIds.has(item.id))
      // 只有真正没有数据时才标记耗尽（不再因 partial batch 停止）
      if (data.length === 0) gridExhausted.value = true
      gridOffset.value += data.length
      gridItems.value = [...gridItems.value, ...uniqueData]
      return data.length
    } finally {
      gridLoading.value = false
    }
  }

  async function loadGridComplete(expectedCount = 0) {
    const expected = Math.max(0, Number(expectedCount || 0))
    const firstLimit = Math.max(BATCH, Math.min(MAX_GRID_PRELOAD, expected || MAX_GRID_PRELOAD))
    let received = await loadGrid(false, firstLimit)
    while (!gridExhausted.value && expected > gridOffset.value && received > 0) {
      received = await loadGrid(true, Math.min(MAX_GRID_PRELOAD, expected - gridOffset.value))
    }
    gridExhausted.value = true
  }

  function setGridQuery(query = {}) {
    gridQuery.value = {
      monitor: query.monitor ?? null,
      dateFrom: query.dateFrom ?? null,
      dateTo: query.dateTo ?? null,
    }
  }

  function openGrid(query = {}) {
    const agent = useAgentStore()
    setGridQuery({
      monitor: Object.prototype.hasOwnProperty.call(query, 'monitor') ? query.monitor : agent.selectedMonitor,
      dateFrom: query.dateFrom ?? null,
      dateTo: query.dateTo ?? null,
    })
    resetGrid()
    gridMode.value = true
    if (query.preloadAll) loadGridComplete(query.expectedCount)
    else loadGrid(false)
  }

  function toggleGridItem(id) {
    const s = new Set(gridSelected.value)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    gridSelected.value = s
  }

  function setGridItemSelected(id, selected = true) {
    const s = new Set(gridSelected.value)
    if (selected) s.add(id)
    else s.delete(id)
    gridSelected.value = s
  }

  function selectOnlyGridItem(id) {
    gridSelected.value = id ? new Set([id]) : new Set()
  }

  function selectAllGrid() {
    if (gridSelected.value.size === gridItems.value.length) {
      gridSelected.value = new Set()
    } else {
      gridSelected.value = new Set(gridItems.value.map(s => s.id))
    }
  }

  function notifyScreenshotsChanged() {
    const agent = useAgentStore()
    window.dispatchEvent(new CustomEvent('screenshots:changed', {
      detail: { agent: agent.selectedAgent },
    }))
  }

  function removeGridItems(ids) {
    const deleted = new Set(ids)
    gridItems.value = gridItems.value.filter(s => !deleted.has(s.id))
    gridOffset.value = gridItems.value.length
    gridSelected.value = new Set([...gridSelected.value].filter(id => !deleted.has(id)))
  }

  async function deleteSelected() {
    const ids = [...gridSelected.value]
    if (!ids.length) return
    await api.deleteScreenshots(ids)
    removeGridItems(ids)
    notifyScreenshotsChanged()
  }

  function resetGrid(options = {}) {
    gridItems.value = []
    gridOffset.value = 0
    gridExhausted.value = false
    gridSelected.value = new Set()
    gridLoading.value = false
    if (options.resetQuery) setGridQuery()
  }

  return {
    liveMode,
    gridMode, gridItems, gridSelected, gridOffset, gridLoading, gridExhausted, gridQuery,
    liveOpen, liveInterval, livePollMs, displaySource, displayItems, displayIndex, currentDisplayItem, BATCH,
    loadLatest, resetLiveInterval, prev, next,
    browseTimeline, browseBrowser, goLive,
    loadGrid, loadGridComplete, setGridQuery, openGrid, toggleGridItem, setGridItemSelected, selectOnlyGridItem, selectAllGrid, deleteSelected, resetGrid,
    removeGridItems, notifyScreenshotsChanged,
  }
})
