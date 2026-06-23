import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'
import { useAgentStore } from './agent'

export const useScreenshotStore = defineStore('screenshot', () => {
  const liveMode = ref(true)
  const screenshotList = ref([])
  const currentIndex = ref(0)
  const gridMode = ref(false)
  const gridItems = ref([])
  const gridSelected = ref(new Set())
  const gridOffset = ref(0)
  const gridLoading = ref(false)
  const gridExhausted = ref(false)
  const liveOpen = ref(false)

  // 浏览模式: 'live' | 'timeline' | 'browser'
  const displaySource = ref('live')
  const displayItems = ref([])  // 带 screenshot_id + title 的条目列表
  const displayIndex = ref(0)

  const BATCH = 30

  const currentDisplayItem = computed(() => displayItems.value[displayIndex.value] || null)

  async function loadLatest() {
    const agent = useAgentStore()
    if (!agent.selectedAgent) return null
    let data
    try {
      data = await api.getLatestScreenshot(agent.selectedAgent, agent.selectedMonitor)
    } catch (err) {
      if (agent.selectedMonitor !== 0) {
        agent.selectMonitor(0)
        data = await api.getLatestScreenshot(agent.selectedAgent, 0)
      } else {
        throw err
      }
    }
    if (data && data.id) {
      agent.setMonitorTotal(data.monitor_total || 1)
    }
    return data
  }

  async function loadHistory() {
    const agent = useAgentStore()
    if (!agent.selectedAgent) return
    screenshotList.value = await api.getScreenshots(agent.selectedAgent, 50, 0, agent.selectedMonitor)
    currentIndex.value = 0
  }

  function prev() {
    if (displayItems.value.length && displaySource.value !== 'live') {
      if (displayIndex.value > 0) displayIndex.value--
      else displayIndex.value = displayItems.value.length - 1 // 循环
    } else {
      if (currentIndex.value > 0) currentIndex.value--
    }
  }

  function next() {
    if (displayItems.value.length && displaySource.value !== 'live') {
      if (displayIndex.value < displayItems.value.length - 1) displayIndex.value++
      else displayIndex.value = 0 // 循环
    } else {
      if (currentIndex.value < screenshotList.value.length - 1) currentIndex.value++
    }
  }

  // 进入时间线浏览模式
  function browseTimeline(items, startIndex) {
    displaySource.value = 'timeline'
    displayItems.value = items.filter(e => e.screenshot_id)
    displayIndex.value = Math.max(0, displayItems.value.findIndex(e => e === items[startIndex]))
    liveMode.value = false
  }

  // 进入浏览器历史浏览模式
  function browseBrowser(items, startIndex) {
    displaySource.value = 'browser'
    displayItems.value = items.filter(r => r.screenshot_id)
    displayIndex.value = Math.max(0, displayItems.value.findIndex(r => r === items[startIndex]))
    liveMode.value = false
  }

  // 回到实时模式
  function goLive() {
    displaySource.value = 'live'
    displayItems.value = []
    displayIndex.value = 0
    liveMode.value = true
  }

  // 回到历史模式
  function goHistory() {
    displaySource.value = 'live'
    displayItems.value = []
    displayIndex.value = 0
    liveMode.value = false
  }

  async function loadGrid(append = false) {
    const agent = useAgentStore()
    if (!agent.selectedAgent || gridLoading.value || (append && gridExhausted.value)) return
    gridLoading.value = true
    try {
      const offset = append ? gridOffset.value : 0
      const data = await api.getScreenshots(agent.selectedAgent, BATCH, offset)
      if (!append) {
        gridItems.value = []
        gridOffset.value = 0
        gridExhausted.value = false
        gridSelected.value = new Set()
      }
      // 只有真正没有数据时才标记耗尽（不再因 partial batch 停止）
      if (data.length === 0) gridExhausted.value = true
      gridOffset.value += data.length
      gridItems.value = [...gridItems.value, ...data]
    } finally {
      gridLoading.value = false
    }
  }

  function toggleGridItem(id) {
    const s = new Set(gridSelected.value)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    gridSelected.value = s
  }

  function selectAllGrid() {
    if (gridSelected.value.size === gridItems.value.length) {
      gridSelected.value = new Set()
    } else {
      gridSelected.value = new Set(gridItems.value.map(s => s.id))
    }
  }

  async function deleteSelected() {
    const ids = [...gridSelected.value]
    if (!ids.length) return
    await api.deleteScreenshots(ids)
    gridSelected.value = new Set()
    await loadGrid(false)
  }

  function resetGrid() {
    gridItems.value = []
    gridOffset.value = 0
    gridExhausted.value = false
    gridSelected.value = new Set()
    gridLoading.value = false
  }

  return {
    liveMode, screenshotList, currentIndex,
    gridMode, gridItems, gridSelected, gridOffset, gridLoading, gridExhausted,
    liveOpen, displaySource, displayItems, displayIndex, currentDisplayItem, BATCH,
    loadLatest, loadHistory, prev, next,
    browseTimeline, browseBrowser, goLive, goHistory,
    loadGrid, toggleGridItem, selectAllGrid, deleteSelected, resetGrid,
  }
})
