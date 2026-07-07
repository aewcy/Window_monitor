const BASE = '/api'
const TAB_SESSION_KEY = 'crkrd_tab_session'
const TAB_SESSION_HEADER = 'X-CRKRD-Tab-Session'
const TAB_SESSION_QUERY = 'tab_session'

export function redirectToLogin(path = window.location.pathname) {
  sessionStorage.removeItem(TAB_SESSION_KEY)
  window.location.replace(`${path}?login=1`)
}

export function getTabSessionToken() {
  return window.__CRKRD_TAB_TOKEN__ || sessionStorage.getItem(TAB_SESSION_KEY) || ''
}

function requireTabSessionToken() {
  const token = getTabSessionToken()
  if (!token) {
    redirectToLogin()
    throw new Error('missing-tab-session')
  }
  return token
}

function withTabSessionHeaders(headers = {}) {
  const token = requireTabSessionToken()
  return {
    ...headers,
    [TAB_SESSION_HEADER]: token,
  }
}

export function appendTabSession(url) {
  const token = requireTabSessionToken()
  const parsed = new URL(url, window.location.origin)
  parsed.searchParams.set(TAB_SESSION_QUERY, token)
  return parsed.origin === window.location.origin
    ? `${parsed.pathname}${parsed.search}${parsed.hash}`
    : parsed.toString()
}

export async function authFetch(url, options = {}) {
  const resp = await fetch(url, {
    cache: 'no-store',
    credentials: 'same-origin',
    ...options,
    headers: withTabSessionHeaders(options.headers || {}),
  })
  if (resp.status === 401) {
    redirectToLogin()
  }
  return resp
}

async function request(path, options = {}) {
  const resp = await authFetch(BASE + path, options)
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
export const sendAgentCommand = (name, command, payload = {}) =>
  request(`/agents/${encodeURIComponent(name)}/commands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, payload }),
  })

// Screenshots
export const getLatestScreenshot = (agent, monitor) => {
  let url = `/screenshots/latest?agent=${encodeURIComponent(agent)}`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}
export const getLatestLiveScreenshot = (agent, monitor, options = {}) => {
  let url = `/screenshots/live/latest?agent=${encodeURIComponent(agent)}`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  if (options.fallback) url += '&fallback=true'
  if (options.fresh) url += '&fresh=true'
  if (options.maxAge) url += `&max_age=${encodeURIComponent(options.maxAge)}`
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
export const getScreenshotImage = (id) => appendTabSession(`/api/screenshots/image/${id}`)
export const getScreenshotThumb = (id) => appendTabSession(`/api/screenshots/thumb/${id}`)
export const getScreenshotPreview = (id) => appendTabSession(`/api/screenshots/preview/${id}`)
export const getScreenshotThumbsBatch = (ids) =>
  request('/screenshots/thumbs-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
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
export const getAppEvents = (agent, limit = 20, offset = 0, monitor = null, dateFrom = null, dateTo = null) => {
  let url = `/app_events?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}&with_screenshots=true`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  if (dateFrom) url += `&date_from=${encodeURIComponent(dateFrom)}`
  if (dateTo) url += `&date_to=${encodeURIComponent(dateTo)}`
  return request(url)
}

// Browser History
export const getBrowserHistory = (agent, limit = 20, offset = 0, monitor = null) => {
  let url = `/browser_history?agent=${encodeURIComponent(agent)}&limit=${limit}&offset=${offset}&with_screenshots=true`
  if (monitor !== null && monitor !== undefined) url += `&monitor=${monitor}`
  return request(url)
}

// Screenshot dates/hours for calendar
export const getScreenshotDates = (agent, dateFrom = null, dateTo = null) => {
  let url = `/screenshots/dates?agent=${encodeURIComponent(agent)}`
  if (dateFrom) url += `&date_from=${encodeURIComponent(dateFrom)}`
  if (dateTo) url += `&date_to=${encodeURIComponent(dateTo)}`
  return request(url)
}
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

// Screenshot rules
export const getScreenshotRules = () => request('/screenshot-rules')
export const createScreenshotRule = (ruleType, pattern, enabled = true) =>
  request('/screenshot-rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rule_type: ruleType, pattern, enabled }),
  })
export const updateScreenshotRule = (id, payload) =>
  request(`/screenshot-rules/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
export const deleteScreenshotRule = (id) =>
  request(`/screenshot-rules/${id}`, { method: 'DELETE' })

// Heartbeat
export const sendHeartbeat = () =>
  authFetch(BASE + '/viewer/heartbeat', { method: 'POST' }).catch(() => {})
