const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(BASE + path, options)
  if (!resp.ok) throw new Error(`${resp.status}`)
  return resp.json()
}

// Agent
export const getAgents = () => request('/agents')
export const renameAgent = (name, displayName) =>
  request(`/agents/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName }),
  })

// Screenshots
export const getLatestScreenshot = (agent, monitor) => {
  let url = `/screenshots/latest?agent=${encodeURIComponent(agent)}`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}
export const getScreenshots = (agent, limit = 50, offset = 0, monitor = null) => {
  let url = `/screenshots?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}`
  if (monitor !== null) url += `&monitor=${monitor}`
  return request(url)
}
export const getScreenshotImage = (id) => `/api/screenshots/image/${id}`
export const deleteScreenshots = (ids) =>
  request('/screenshots/delete-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })

// App Events
export const getAppEvents = (agent, limit = 20) =>
  request(`/app_events?agent=${encodeURIComponent(agent)}&limit=${limit}&with_screenshots=true`)

// Browser History
export const getBrowserHistory = (agent, limit = 20) =>
  request(`/browser_history?agent=${encodeURIComponent(agent)}&limit=${limit}&with_screenshots=true`)

// Logs
export const getLogs = (limit = 20) => request(`/logs?limit=${limit}`)

// Stats
export const getStats = (agent = null) => {
  let url = '/dashboard/stats'
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  return request(url)
}

// Heartbeat
export const sendHeartbeat = () =>
  fetch(BASE + '/viewer/heartbeat', { method: 'POST' }).catch(() => {})
