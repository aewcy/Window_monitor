import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'

export const useAgentStore = defineStore('agent', () => {
  const agents = ref([])
  const selectedAgent = ref(null)
  const selectedMonitor = ref(0)
  const monitorTotal = ref(1)

  const selectedAgentData = computed(() =>
    agents.value.find(a => a.name === selectedAgent.value)
  )

  async function loadAgents() {
    agents.value = await api.getAgents()
    if (!selectedAgent.value && agents.value.length) {
      selectAgent(agents.value[0].name)
    }
  }

  function selectAgent(name) {
    selectedAgent.value = name
    const saved = Number(localStorage.getItem(`monitor:${name}`))
    selectedMonitor.value = Number.isInteger(saved) && saved >= 0 ? saved : 0
    monitorTotal.value = 1
  }

  function selectMonitor(idx) {
    selectedMonitor.value = idx
    if (selectedAgent.value) {
      localStorage.setItem(`monitor:${selectedAgent.value}`, String(idx))
    }
  }

  function setMonitorTotal(total) {
    monitorTotal.value = Math.max(1, total || 1)
    if (selectedMonitor.value >= monitorTotal.value) {
      selectMonitor(0)
    }
  }

  async function rename(name, displayName) {
    await api.renameAgent(name, displayName)
    await loadAgents()
  }

  return {
    agents, selectedAgent, selectedMonitor, monitorTotal,
    selectedAgentData, loadAgents, selectAgent, selectMonitor, setMonitorTotal, rename,
  }
})
