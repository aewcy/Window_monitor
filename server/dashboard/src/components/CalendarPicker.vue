<script setup>
import { ref, computed, watch } from 'vue'
import * as api from '../api'
import { useAgentStore } from '../stores/agent'
import { useScreenshotStore } from '../stores/screenshot'

const agent = useAgentStore()
const ss = useScreenshotStore()

const open = ref(false)
const dates = ref([])       // [{date: '2025-06-12', count: 42}, ...]
const hours = ref([])       // [{hour: 9, count: 12}, ...]
const selectedDate = ref(null)
const selectedHour = ref(null)
const loading = ref(false)

const today = new Date()
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth()) // 0-indexed

const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
const WEEKDAYS = ['日','一','二','三','四','五','六']

const dateSet = computed(() => new Set(dates.value.map(d => d.date)))

const calendarDays = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value, 1)
  const last = new Date(viewYear.value, viewMonth.value + 1, 0)
  const days = []
  // leading blanks
  for (let i = 0; i < first.getDay(); i++) days.push(null)
  for (let d = 1; d <= last.getDate(); d++) {
    const ds = `${viewYear.value}-${String(viewMonth.value+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`
    days.push({ day: d, date: ds, hasData: dateSet.value.has(ds) })
  }
  return days
})

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value-- }
  else viewMonth.value--
}

function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++ }
  else viewMonth.value++
}

async function loadDates() {
  if (!agent.selectedAgent) return
  try {
    dates.value = await api.getScreenshotDates(agent.selectedAgent)
  } catch { dates.value = [] }
}

async function selectDate(day) {
  if (!day || !day.hasData) return
  selectedDate.value = day.date
  selectedHour.value = null
  try {
    hours.value = await api.getScreenshotHours(agent.selectedAgent, day.date)
  } catch { hours.value = [] }
}

async function applyFilter() {
  if (!selectedDate.value) return
  loading.value = true
  try {
    const agent2 = useAgentStore()
    let dateFrom = selectedDate.value
    let dateTo = selectedDate.value
    if (selectedHour.value !== null) {
      dateFrom = `${selectedDate.value} ${String(selectedHour.value).padStart(2,'0')}:00:00`
      dateTo = `${selectedDate.value} ${String(selectedHour.value).padStart(2,'0')}:59:59`
    }
    // 直接用 API 加载截图列表
    const data = await api.getScreenshots(agent2.selectedAgent, 2000, 0)
    // 按日期筛选
    const filtered = data.filter(s => {
      const ts = s.timestamp || ''
      if (selectedHour.value !== null) {
        return ts >= dateFrom && ts <= dateTo
      }
      return ts.startsWith(selectedDate.value)
    })
    ss.screenshotList = filtered
    ss.currentIndex = 0
    ss.liveMode = false
    open.value = false
  } finally { loading.value = false }
}

function clearFilter() {
  selectedDate.value = null
  selectedHour.value = null
  hours.value = []
  ss.liveMode = true
  open.value = false
}

function toggle() {
  open.value = !open.value
  if (open.value) loadDates()
}

// 点击外部关闭
function onDocClick(e) {
  if (!e.target.closest('.cal-wrap')) open.value = false
}

watch(open, v => {
  if (v) document.addEventListener('click', onDocClick, { capture: true })
  else document.removeEventListener('click', onDocClick, { capture: true })
})
</script>

<template>
  <div class="cal-wrap">
    <button class="cal-btn" :class="{ active: open }" @click.stop="toggle" title="按日期查看">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
    </button>
    <div v-if="open" class="cal-panel" @click.stop>
      <div class="cal-nav">
        <button @click="prevMonth" class="cal-arrow">◀</button>
        <span class="cal-title">{{ viewYear }}年 {{ MONTHS[viewMonth] }}</span>
        <button @click="nextMonth" class="cal-arrow">▶</button>
      </div>
      <div class="cal-weekdays">
        <span v-for="w in WEEKDAYS" :key="w">{{ w }}</span>
      </div>
      <div class="cal-grid">
        <div v-for="(d, i) in calendarDays" :key="i"
          class="cal-day" :class="{
            empty: !d,
            hasData: d?.hasData,
            selected: d?.date === selectedDate
          }" @click="d && selectDate(d)">
          <span v-if="d">{{ d.day }}</span>
        </div>
      </div>
      <div v-if="hours.length" class="cal-hours">
        <div class="cal-hours-title">选择时段</div>
        <div class="cal-hour-grid">
          <button v-for="h in hours" :key="h.hour"
            class="cal-hour-btn" :class="{ selected: selectedHour === h.hour }"
            @click="selectedHour = (selectedHour === h.hour ? null : h.hour)">
            {{ String(h.hour).padStart(2,'0') }}:00 <span class="cal-hour-count">({{ h.count }})</span>
          </button>
        </div>
      </div>
      <div v-if="selectedDate" class="cal-actions">
        <button class="cal-apply" @click="applyFilter" :disabled="loading">
          {{ loading ? '加载中...' : '查看' }}
        </button>
        <button class="cal-clear" @click="clearFilter">清除</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cal-wrap { position: relative; }
.cal-btn {
  background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
  color: var(--text-secondary); padding: 6px 8px; cursor: pointer; transition: all .15s;
  display: flex; align-items: center;
}
.cal-btn:hover, .cal-btn.active { background: var(--surface-hover); color: var(--text); }
.cal-panel {
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 100;
  background: #1a1a2e; border: 1px solid var(--hairline); border-radius: var(--radius-md);
  padding: 12px; min-width: 280px; box-shadow: var(--shadow-lift);
}
.cal-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.cal-arrow { background: none; border: none; color: var(--muted); cursor: pointer; padding: 4px 8px; font-size: 10px; }
.cal-arrow:hover { color: var(--text); }
.cal-title { font-size: 12px; font-weight: 600; color: var(--text); }
.cal-weekdays { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; margin-bottom: 4px; }
.cal-weekdays span { text-align: center; font-size: 9px; color: var(--muted); padding: 2px; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.cal-day {
  text-align: center; padding: 4px; font-size: 11px; border-radius: 6px;
  color: var(--muted); cursor: default; transition: all .1s;
}
.cal-day.empty { visibility: hidden; }
.cal-day.hasData { color: var(--text); cursor: pointer; }
.cal-day.hasData:hover { background: var(--surface-hover); }
.cal-day.selected { background: var(--accent); color: #fff; font-weight: 600; }
.cal-day.hasData::after {
  content: ''; display: block; width: 4px; height: 4px; border-radius: 50%;
  background: var(--accent); margin: 1px auto 0;
}
.cal-day.selected::after { background: rgba(255,255,255,.6); }
.cal-hours { margin-top: 8px; border-top: 1px solid var(--hairline); padding-top: 8px; }
.cal-hours-title { font-size: 10px; color: var(--muted); margin-bottom: 6px; }
.cal-hour-grid { display: flex; flex-wrap: wrap; gap: 4px; }
.cal-hour-btn {
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 6px;
  color: var(--text-secondary); font-size: 10px; padding: 3px 8px; cursor: pointer; transition: all .1s;
}
.cal-hour-btn:hover { background: var(--surface-hover); }
.cal-hour-btn.selected { background: var(--accent); color: #fff; border-color: var(--accent); }
.cal-hour-count { color: var(--muted); }
.cal-actions { display: flex; gap: 8px; margin-top: 10px; }
.cal-apply {
  flex: 1; background: var(--accent); color: #fff; border: none; border-radius: 6px;
  padding: 6px; font-size: 11px; font-weight: 600; cursor: pointer;
}
.cal-apply:disabled { opacity: .5; cursor: not-allowed; }
.cal-clear {
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 6px;
  color: var(--text-secondary); padding: 6px 12px; font-size: 11px; cursor: pointer;
}
.cal-clear:hover { background: var(--surface-hover); }
</style>
