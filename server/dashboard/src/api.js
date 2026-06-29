const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(BASE + path, {
    cache: 'no-store',
    ...options,
  })
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
export const allowAgentUpdate = (name) =>
  request(`/agents/${encodeURIComponent(name)}/update/allow`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
export const pauseAgentUpdate = (name) =>
  request(`/agents/${encodeURIComponent(name)}/update/pause`, { method: 'POST' })
export const getAgentVersion = () => request('/agent/version')

// Screenshots
export const getLatestScreenshot = (agent, monitor) => {
  let url = `/screenshots/latest?agent=${encodeURIComponent(agent)}`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}
export const getLatestLiveScreenshot = (agent, monitor, fallback = false) => {
  let url = `/screenshots/live/latest?agent=${encodeURIComponent(agent)}`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  if (fallback) url += '&fallback=true'
  return request(url)
}
export const getLiveScreenshotImage = (s) =>
  s?.image_base64 ? `data:image/${s.format || 'jpeg'};base64,${s.image_base64}` : null
export const getScreenshots = (agent, limit = 50, offset = 0, monitor = null, dateFrom = null, dateTo = null) => {
  let url = `/screenshots?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}`
  if (monitor !== null) url += `&monitor=${monitor}`
  if (dateFrom) url += `&date_from=${encodeURIComponent(dateFrom)}`
  if (dateTo) url += `&date_to=${encodeURIComponent(dateTo)}`
  return request(url)
}
export const getScreenshotImage = (id) => `/api/screenshots/image/${id}`
export const deleteScreenshots = (ids) =>
  request('/screenshots/delete-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
export const deleteScreenshotsRange = (agent, dateFrom, dateTo, monitor = null) =>
  request('/screenshots/delete-range', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, date_from: dateFrom, date_to: dateTo, monitor }),
  })

// App Events
export const getAppEvents = (agent, limit = 20, offset = 0, monitor = null) => {
  let url = `/app_events?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}&with_screenshots=true`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}

// Browser History
export const getBrowserHistory = (agent, limit = 20, offset = 0, monitor = null) => {
  let url = `/browser_history?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}&with_screenshots=true`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}

// Screenshot dates/hours for calendar
export const getScreenshotDates = (agent) =>
  request(`/screenshots/dates?agent=${encodeURIComponent(agent)}`)
export const getScreenshotHours = (agent, date) =>
  request(`/screenshots/hours?agent=${encodeURIComponent(agent)}&date=${encodeURIComponent(date)}`)

// Logs
export const getLogs = (limit = 20) => request(`/logs?limit=${limit}`)

// Stats
export const getStats = (agent = null) => {
  let url = '/dashboard/stats'
  if (agent) url += `?agent=${encodeURIComponent(agent)}`
  return request(url)
}
export const getStorageStats = () => request('/storage/stats')

// Heartbeat
export const sendHeartbeat = () =>
  fetch(BASE + '/viewer/heartbeat', { method: 'POST', cache: 'no-store' }).catch(() => {})
