import { ref, onUnmounted } from 'vue'
import * as api from '../api'

export function usePolling() {
  let heartbeatTimer = null
  let fastTimer = null
  let slowTimer = null

  function startHeartbeat() {
    stopHeartbeat()
    api.sendHeartbeat()
    heartbeatTimer = setInterval(() => api.sendHeartbeat(), 1000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  }

  function startFast(callback, interval = 1000) {
    stopFast()
    callback()
    fastTimer = setInterval(callback, interval)
  }

  function stopFast() {
    if (fastTimer) { clearInterval(fastTimer); fastTimer = null }
  }

  function startSlow(callback, interval = 5000) {
    stopSlow()
    callback()
    slowTimer = setInterval(callback, interval)
  }

  function stopSlow() {
    if (slowTimer) { clearInterval(slowTimer); slowTimer = null }
  }

  function stopAll() {
    stopHeartbeat()
    stopFast()
    stopSlow()
  }

  onUnmounted(stopAll)

  return { startHeartbeat, stopHeartbeat, startFast, stopFast, startSlow, stopSlow, stopAll }
}
