<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import { useAgentStore } from '../stores/agent'
import { getScreenshotImage } from '../api'

const ss = useScreenshotStore()
const agent = useAgentStore()
const imgSrc = ref(null)

// FPS 标签 (根据截图间隔显示)
const fpsLabel = computed(() => {
  const data = agent.selectedAgentData
  if (!data || !data.screenshot_interval) return null
  const iv = data.screenshot_interval
  if (iv <= 0.5) return '4fps'
  if (iv <= 2) return '1fps'
  if (iv <= 10) return '1/5s'
  return '1/min'
})

// 浏览模式下的当前项 (活动记录/浏览器历史叠加层)
const currentItem = computed(() => ss.currentDisplayItem)
const isBrowse = computed(() => ss.displaySource !== 'live')
// 历史模式 (日历筛选后)
const isHistory = computed(() => !ss.liveMode && ss.screenshotList.length > 0)
// 需要显示标题和导航的状态 (浏览模式或历史模式)
const showBrowseUI = computed(() => isBrowse.value || isHistory.value)

const sourceLabel = computed(() => {
  if (ss.displaySource === 'timeline') return '活动'
  if (ss.displaySource === 'browser') return '浏览'
  if (isHistory.value) return '历史'
  return 'Live'
})

const itemIndex = computed(() => {
  if (isBrowse.value) return `${ss.displayIndex + 1}/${ss.displayItems.length}`
  if (isHistory.value) return `${ss.currentIndex + 1}/${ss.screenshotList.length}`
  return ''
})

const itemTitle = computed(() => {
  if (ss.displaySource === 'timeline' && currentItem.value) {
    return `${currentItem.value.process_name} — ${currentItem.value.window_title}`
  }
  if (ss.displaySource === 'browser' && currentItem.value) {
    return currentItem.value.title || currentItem.value.url
  }
  if (isHistory.value && ss.screenshotList[ss.currentIndex]) {
    const s = ss.screenshotList[ss.currentIndex]
    return (s.timestamp || '').replace('T', ' ')
  }
  return ''
})

const currentHistoryItem = computed(() => ss.screenshotList[ss.currentIndex] || null)

// 加载截图
async function loadLive() {
  const data = await ss.loadLatest()
  if (data && data.id) {
    imgSrc.value = getScreenshotImage(data.id)
  }
}

function loadBrowseItem() {
  const item = currentItem.value
  if (item && item.screenshot_id) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
  }
}

function loadHistoryItem() {
  const item = currentHistoryItem.value
  if (item && item.id) {
    imgSrc.value = getScreenshotImage(item.id)
  }
}

// 监听 overlay 打开
watch(() => ss.liveOpen, (v) => {
  if (v) {
    if (isBrowse.value) loadBrowseItem()
    else if (isHistory.value) loadHistoryItem()
    else loadLive()
  }
})

// 监听浏览模式下的当前项变化 (timeline/browser)
watch(() => ss.currentDisplayItem, (item) => {
  if (item && item.screenshot_id && ss.liveOpen) {
    imgSrc.value = getScreenshotImage(item.screenshot_id)
  }
}, { immediate: true })

// 监听历史模式下的当前截图变化 (日历筛选，同时支持嵌入式卡片和 overlay)
watch([currentHistoryItem, isHistory], ([item, hist]) => {
  if (hist && !isBrowse.value && item && item.id) {
    imgSrc.value = getScreenshotImage(item.id)
  }
})

// 监听日历筛选结果 (screenshotList 变化时，自动显示第一张)
watch(() => ss.screenshotList, (list) => {
  if (list.length && !isBrowse.value) {
    loadHistoryItem()
  }
})

// 嵌入式卡片初始化: 加载最新截图
onMounted(() => {
  if (!isBrowse.value && !isHistory.value && agent.selectedAgent) {
    loadLive()
  }
})

// 监听 Agent 切换: 自动加载最新截图 (仅嵌入式卡片)
watch(() => agent.selectedAgent, (name) => {
  if (name && !isBrowse.value && !isHistory.value && !ss.liveOpen) {
    loadLive()
  }
})

// 监听实时模式恢复: 重新加载最新截图
watch(() => ss.liveMode, (live) => {
  if (live && !ss.liveOpen && agent.selectedAgent) {
    loadLive()
  }
})

function close() {
  ss.liveOpen = false
  ss.goLive()  // 关闭时回到实时模式
}

function goLive() {
  ss.goLive()
  loadLive()
}

function prev() {
  ss.prev()
}

function next() {
  ss.next()
}
</script>

<template>
  <div class="live-overlay" :class="{ open: ss.liveOpen }" @click.self="close">
    <div class="live-box">
      <div class="live-header">
        <span class="live-title">
          <span v-if="!showBrowseUI" class="live-dot"></span>
          <span v-if="!showBrowseUI" class="live-text">Live</span>
          <span v-else class="browse-tag">{{ sourceLabel }} {{ itemIndex }}</span>
          <span class="agent-name">{{ agent.selectedAgent }}</span>
        </span>
        <div class="header-actions">
          <button v-if="showBrowseUI" class="live-btn" @click="goLive">
            <span class="live-dot-sm"></span> 实时
          </button>
          <button class="close-btn" @click="close">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
            关闭
          </button>
        </div>
      </div>
      <div class="live-body">
        <img v-if="imgSrc" :src="imgSrc" class="live-img" :key="imgSrc" />
        <div v-else class="placeholder"><span class="big">[ ]</span>暂无截图</div>
        <div class="fps-badge" v-if="fpsLabel && !showBrowseUI">{{ fpsLabel }}</div>
        <div class="mon-chips" v-if="agent.monitorTotal > 1 && !showBrowseUI">
          <button v-for="i in agent.monitorTotal" :key="i"
            class="mon-chip" :class="{ active: agent.selectedMonitor === i-1 }"
            @click="agent.selectMonitor(i-1)">屏{{ i }}</button>
        </div>
        <div class="item-title" v-if="itemTitle">
          <span class="title-text">{{ itemTitle }}</span>
        </div>
        <div class="nav" v-if="showBrowseUI && (ss.displayItems.length > 1 || ss.screenshotList.length > 1)">
          <button class="nav-pill" @click="prev">◀ 上一个</button>
          <button class="nav-pill" @click="next">下一个 ▶</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.live-overlay {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(8px);
  opacity: 0; pointer-events: none; transition: opacity .25s cubic-bezier(0.22,1,0.36,1);
}
.live-overlay.open { opacity: 1; pointer-events: auto; }
.live-box {
  width: 70vw; height: 70vh; background: var(--ground);
  border: 1px solid var(--hairline); border-radius: var(--radius-lg);
  overflow: hidden; display: flex; flex-direction: column;
  box-shadow: 0 32px 80px rgba(0,0,0,0.6);
  transform: scale(0.92); transition: transform .3s cubic-bezier(0.22,1,0.36,1);
}
.live-overlay.open .live-box { transform: scale(1); }
.live-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--hairline); flex-shrink: 0;
}
.live-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 1.5s infinite; }
.live-dot-sm { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 1.5s infinite; }
.live-text { color: var(--green); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; font-weight: 700; }
.browse-tag { font-family: var(--font-mono); color: var(--purple); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.agent-name { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.live-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid rgba(74,222,128,.3); border-radius: 6px;
  background: rgba(74,222,128,.08); color: var(--green); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 6px;
}
.live-btn:hover { background: rgba(74,222,128,.15); border-color: var(--green); }
.close-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 4px 12px; border: 1px solid var(--hairline); border-radius: 6px;
  background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 4px;
}
.close-btn:hover { border-color: var(--red); color: var(--red); }
.live-body { flex: 1; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.3); position: relative; }
.live-img { max-width: 100%; max-height: 100%; object-fit: contain; }
.placeholder { text-align: center; color: var(--muted); }
.placeholder .big { font-size: 64px; opacity: 0.1; display: block; margin-bottom: 12px; }
.mon-chips { position: absolute; top: 12px; left: 16px; display: flex; gap: 6px; }
.mon-chip {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 3px 10px; border-radius: 20px; border: 1px solid var(--hairline);
  color: var(--muted); background: rgba(0,0,0,0.5); cursor: pointer; transition: all .15s;
}
.mon-chip:hover { border-color: var(--blue); color: var(--blue); }
.mon-chip.active { border-color: var(--blue); color: var(--blue); background: rgba(96,165,250,.15); }
.item-title {
  position: absolute; bottom: 56px; left: 50%; transform: translateX(-50%);
  max-width: 80%; text-align: center;
}
.title-text {
  font-family: var(--font-mono); font-size: 12px; font-weight: 500;
  padding: 5px 16px; background: rgba(0,0,0,0.65); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary);
  backdrop-filter: blur(8px); display: inline-block;
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.nav { position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
.nav-pill {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  padding: 6px 18px; background: rgba(255,255,255,0.08); border: 1px solid var(--hairline);
  border-radius: 20px; color: var(--text-secondary); cursor: pointer; backdrop-filter: blur(8px); transition: all .15s;
}
.nav-pill:hover { background: rgba(255,255,255,0.14); color: var(--text); border-color: rgba(255,255,255,0.2); }
.fps-badge {
  position: absolute; top: 12px; right: 16px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 3px 10px; border-radius: 12px;
  background: rgba(0,0,0,0.6); color: var(--green);
  border: 1px solid rgba(74,222,128,.2); backdrop-filter: blur(8px);
  pointer-events: none;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
