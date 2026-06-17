import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'

export const useAgentStore = defineStore('agent', () => {
  const agents = ref([])
  const selectedAgent = ref(null)
  const selectedMonitor = ref(null)
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
    selectedMonitor.value = null
    monitorTotal.value = 1
  }

  function selectMonitor(idx) {
    selectedMonitor.value = idx
  }

  async function rename(name, displayName) {
    await api.renameAgent(name, displayName)
    await loadAgents()
  }

  return {
    agents, selectedAgent, selectedMonitor, monitorTotal,
    selectedAgentData, loadAgents, selectAgent, selectMonitor, rename,
  }
})
