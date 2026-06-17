import { defineStore } from 'pinia'
import { ref } from 'vue'
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
  const displayId = ref(null)  // 点击时间线/浏览器行时显示特定截图

  const BATCH = 30

  async function loadLatest() {
    const agent = useAgentStore()
    if (!agent.selectedAgent) return null
    const data = await api.getLatestScreenshot(agent.selectedAgent, agent.selectedMonitor)
    if (data && data.id) {
      agent.monitorTotal = data.monitor_total || 1
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
    if (currentIndex.value > 0) currentIndex.value--
  }

  function next() {
    if (currentIndex.value < screenshotList.value.length - 1) currentIndex.value++
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
      if (data.length < BATCH) gridExhausted.value = true
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

  function showById(id) {
    displayId.value = id
  }

  function clearDisplay() {
    displayId.value = null
  }

  return {
    liveMode, screenshotList, currentIndex,
    gridMode, gridItems, gridSelected, gridOffset, gridLoading, gridExhausted,
    liveOpen, displayId, BATCH,
    loadLatest, loadHistory, prev, next,
    loadGrid, toggleGridItem, selectAllGrid, deleteSelected, resetGrid,
    showById, clearDisplay,
  }
})
