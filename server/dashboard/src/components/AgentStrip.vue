<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useAgentStore } from '../stores/agent'
import { allowAgentUpdate, authFetch, getAgentVersion, pauseAgentUpdate, renameAgent, sendAgentCommand } from '../api'

const agent = useAgentStore()

// 右键菜单状态
const ctxMenu = ref({ show: false, x: 0, y: 0, agent: null })

// 重命名状态
const renaming = ref({ show: false, agent: null, name: '' })

// 删除确认状态
const deleting = ref({ show: false, agent: null })
const latestVersion = ref('')

const activeUpdateStatuses = new Set([
  'claimed',
  'downloading',
  'downloaded',
  'installing',
  'restarting',
  'waiting_login',
  'verifying',
])
const terminalUpdateStatuses = new Set([
  'verified',
  'failed',
  'rolled_back_verified',
  'rolled_back_unverified',
  'stale',
  'canceled',
])
const activeUpdateAgent = computed(() =>
  agent.agents.find(a => activeUpdateStatuses.has(a?.update_job?.status || a?.update_status))
)

function onContext(e, a) {
  e.preventDefault()
  ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, agent: a }
}

function closeCtx() {
  ctxMenu.value.show = false
}

function startRename() {
  const a = ctxMenu.value.agent
  renaming.value = { show: true, agent: a, name: a.display_name || a.name }
  closeCtx()
}

async function confirmRename() {
  if (!renaming.value.name.trim()) return
  try {
    await renameAgent(renaming.value.agent.name, renaming.value.name.trim())
    await agent.fetchAgents()
  } catch (e) {
    console.error('Rename failed:', e)
  }
  renaming.value.show = false
}

function cancelRename() {
  renaming.value.show = false
}

function startDelete() {
  deleting.value = { show: true, agent: ctxMenu.value.agent }
  closeCtx()
}

async function allowUpdate() {
  const a = ctxMenu.value.agent
  if (!a) return
  try {
    await allowAgentUpdate(a.name)
    await agent.fetchAgents()
  } catch (e) {
    console.error('Allow update failed:', e)
  }
  closeCtx()
}

async function pauseUpdate() {
  const a = ctxMenu.value.agent
  if (!a) return
  try {
    await pauseAgentUpdate(a.name)
    await agent.fetchAgents()
  } catch (e) {
    console.error('Pause update failed:', e)
  }
  closeCtx()
}

function isCapturePaused(a) {
  return a?.control_status === 'paused'
}

async function toggleCapture() {
  const a = ctxMenu.value.agent
  if (!a) return
  try {
    await sendAgentCommand(a.name, isCapturePaused(a) ? 'resume_capture' : 'pause_capture')
    await agent.fetchAgents()
  } catch (e) {
    console.error('Agent command failed:', e)
  }
  closeCtx()
}

function updateLabel(a) {
  return a?.agent_version ? `v${a.agent_version}` : '未上报版本'
}

function updateState(a) {
  const job = a?.update_job || null
  const status = job?.status || a?.update_status || ''
  const target = job?.target_version || a?.update_target_version || a?.update_allowed_version || latestVersion.value
  const targetText = target ? ` v${target}` : ''
  if (a?.status !== 'online' && activeUpdateStatuses.has(status) && status !== 'waiting_login') {
    return `离线，更新中断${targetText}`
  }
  if (status === 'pending') return a?.status === 'online' ? `等待拉取${targetText}` : `离线，等待上线${targetText}`
  if (status === 'claimed') return `已领取${targetText}`
  if (status === 'downloading') return `下载中${targetText}`
  if (status === 'downloaded') return `下载完成${targetText}`
  if (status === 'installing') return `安装中${targetText}`
  if (status === 'restarting') return `重启中${targetText}`
  if (status === 'waiting_login') return `等待登录验证${targetText}`
  if (status === 'verifying') return `验证中${targetText}`
  if (status === 'verified') return `已验证${targetText}`
  if (status === 'updated') return `文件已替换，待验证${targetText}`
  if (status === 'failed' && a?.update_allowed_version) return `更新失败，待重试${targetText}`
  if (status === 'failed') return `更新失败${targetText}`
  if (status === 'rolled_back_verified') return `已回滚验证${targetText}`
  if (status === 'rolled_back_unverified') return `已回滚待确认${targetText}`
  if (status === 'rolled_back') return `旧回滚状态${targetText}`
  if (status === 'stale') return `更新卡住${targetText}`
  if (status === 'canceled') return `已取消${targetText}`
  if (a?.update_allowed_version) return `等待拉取 v${a.update_allowed_version}`
  return ''
}

function updateStateClass(a) {
  const status = a?.update_job?.status || a?.update_status || ''
  if (a?.status !== 'online' && activeUpdateStatuses.has(status) && status !== 'waiting_login') return 'danger'
  if (status === 'failed' || status === 'stale' || status === 'rolled_back_unverified' || status === 'rolled_back') return 'danger'
  if (activeUpdateStatuses.has(status)) return 'active'
  if (status === 'pending' || a?.update_allowed_version) return 'pending'
  if (terminalUpdateStatuses.has(status)) return status === 'verified' || status === 'rolled_back_verified' ? 'ok' : 'danger'
  return ''
}

function readableUpdateError(error) {
  const text = String(error || '').trim()
  if (!text) return ''
  if (
    text.includes('ConnectionResetError')
    || text.includes('Connection broken')
    || text.includes('10054')
  ) {
    return '更新连接中断，等待 Agent 重试或重启后回报'
  }
  return text.length > 120 ? `${text.slice(0, 120)}...` : text
}

function updateTitle(a) {
  const lines = [
    `当前版本: ${a?.agent_version ? `v${a.agent_version}` : '未上报'}`,
  ]
  if (a?.update_target_version) lines.push(`目标版本: v${a.update_target_version}`)
  if (a?.update_allowed_version) lines.push(`允许更新: v${a.update_allowed_version}`)
  if (a?.update_job?.job_id) lines.push(`更新任务: ${a.update_job.job_id}`)
  if (a?.update_status) lines.push(`更新状态: ${a.update_status}`)
  if (a?.update_progress_bytes || a?.update_total_bytes) {
    lines.push(`下载进度: ${Math.round((a.update_progress_bytes || 0) / 1024 / 1024)} / ${Math.round((a.update_total_bytes || 0) / 1024 / 1024)} MB`)
  }
  if (a?.update_checked_at) lines.push(`最近检查: ${a.update_checked_at}`)
  lines.push(`运行控制: ${isCapturePaused(a) ? '已暂停采集' : '采集中'}`)
  const error = readableUpdateError(a?.update_error)
  if (error) lines.push(`错误: ${error}`)
  return lines.join('\n')
}

async function confirmDelete() {
  try {
    const resp = await authFetch(`/api/agents/${encodeURIComponent(deleting.value.agent.name)}`, { method: 'DELETE' })
    if (resp.ok) {
      await agent.fetchAgents()
      if (agent.selectedAgent === deleting.value.agent.name && agent.agents.length) {
        agent.selectAgent(agent.agents[0].name)
      }
    }
  } catch (e) {
    console.error('Delete failed:', e)
  }
  deleting.value.show = false
}

function cancelDelete() {
  deleting.value.show = false
}

// ESC 关闭所有弹窗
function onKey(e) {
  if (e.key === 'Escape') {
    if (renaming.value.show) cancelRename()
    else if (deleting.value.show) cancelDelete()
    else closeCtx()
  }
}

// 点击空白关闭右键菜单
function onDocClick() {
  closeCtx()
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
  document.addEventListener('click', onDocClick)
  getAgentVersion().then(v => { latestVersion.value = v.version || '' }).catch(() => {})
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('click', onDocClick)
})
</script>

<template>
  <div class="agent-strip">
    <div v-for="a in agent.agents" :key="a.name"
      class="agent-pill" :class="{ active: agent.selectedAgent === a.name }"
      :title="updateTitle(a)"
      @click="agent.selectAgent(a.name)"
      @contextmenu="onContext($event, a)">
      <span class="dot" :class="a.status === 'online' ? 'online' : 'offline'"></span>
      <span class="name">{{ a.display_name || a.name }}</span>
      <span class="meta">{{ updateLabel(a) }}</span>
      <span v-if="isCapturePaused(a)" class="control-badge paused">已暂停采集</span>
      <span v-if="updateState(a)" class="update-badge" :class="updateStateClass(a)">{{ updateState(a) }}</span>
      <span class="meta">{{ a.screenshot_interval ? a.screenshot_interval + 's' : (a.status === 'online' ? '在线' : '离线') }}</span>
    </div>
    <div v-if="!agent.agents.length" class="agent-pill" style="opacity:0.5">
      <span class="name">暂无被控端</span>
    </div>
  </div>

  <!-- 右键菜单 -->
  <Teleport to="body">
    <div v-if="ctxMenu.show" class="ctx-menu" :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }" @click.stop>
      <div class="ctx-item" @click="startRename">
        <span class="ctx-icon">✏️</span>
        <span>改名</span>
      </div>
      <div class="ctx-item" :class="{ disabled: activeUpdateAgent && activeUpdateAgent.name !== ctxMenu.agent?.name }" @click="!(activeUpdateAgent && activeUpdateAgent.name !== ctxMenu.agent?.name) && allowUpdate()">
        <span class="ctx-icon">⬆️</span>
        <span>{{ activeUpdateAgent && activeUpdateAgent.name !== ctxMenu.agent?.name ? '已有机器正在更新' : `允许更新到 v${latestVersion || 'latest'}` }}</span>
      </div>
      <div class="ctx-item" @click="pauseUpdate">
        <span class="ctx-icon">⏸️</span>
        <span>暂停更新</span>
      </div>
      <div class="ctx-item" :class="{ disabled: ctxMenu.agent?.status !== 'online' }" @click="ctxMenu.agent?.status === 'online' && toggleCapture()">
        <span class="ctx-icon">{{ isCapturePaused(ctxMenu.agent) ? '▶️' : '⏸️' }}</span>
        <span>{{ isCapturePaused(ctxMenu.agent) ? '恢复采集' : '暂停采集' }}</span>
      </div>
      <div class="ctx-item danger" @click="startDelete">
        <span class="ctx-icon">🗑️</span>
        <span>删除</span>
      </div>
    </div>
  </Teleport>

  <!-- 重命名弹窗 -->
  <Teleport to="body">
    <div v-if="renaming.show" class="modal-mask" @click.self="cancelRename">
      <div class="modal-box">
        <div class="modal-title">改名</div>
        <div class="modal-desc">{{ renaming.agent?.name }}</div>
        <input v-model="renaming.name" class="modal-input" placeholder="输入显示名称"
          @keydown.enter="confirmRename" @keydown.esc="cancelRename" autofocus />
        <div class="modal-actions">
          <button class="btn" @click="cancelRename">取消</button>
          <button class="btn primary" @click="confirmRename">确定</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 删除确认弹窗 -->
  <Teleport to="body">
    <div v-if="deleting.show" class="modal-mask" @click.self="cancelDelete">
      <div class="modal-box">
        <div class="modal-title">删除被控端</div>
        <div class="modal-desc">
          确定删除 <strong>{{ deleting.agent?.display_name || deleting.agent?.name }}</strong>？<br>
          <span style="color:var(--muted);font-size:12px">将删除该机器的所有截图、活动记录和浏览器历史，不可恢复。</span>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="cancelDelete">取消</button>
          <button class="btn danger" @click="confirmDelete">删除</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.agent-strip { display: flex; gap: 10px; padding: 10px 24px 0; overflow-x: auto; position: relative; z-index: 1; }
.agent-pill {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-md);
  cursor: pointer; transition: all .2s cubic-bezier(0.22,1,0.36,1); white-space: nowrap; flex-shrink: 0;
  user-select: none;
}
.agent-pill:hover { background: var(--surface-hover); transform: translateY(-2px); box-shadow: var(--shadow-card); }
.agent-pill.active { border-color: var(--accent); background: rgba(255,99,99,.08); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.online { background: var(--green); box-shadow: 0 0 6px rgba(74,222,128,.4); }
.dot.offline { background: var(--muted); }
.name { font-size: 12px; font-weight: 600; }
.meta { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.update-badge {
  padding: 2px 6px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  font-size: 10px;
  color: var(--muted);
  background: rgba(255,255,255,.04);
}
.control-badge {
  padding: 2px 6px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  font-size: 10px;
}
.control-badge.paused {
  color: #fca5a5;
  border-color: rgba(252,165,165,.35);
  background: rgba(252,165,165,.08);
}
.update-badge.pending {
  color: #fde68a;
  border-color: rgba(253,230,138,.35);
  background: rgba(253,230,138,.08);
}
.update-badge.active {
  color: #93c5fd;
  border-color: rgba(147,197,253,.35);
  background: rgba(147,197,253,.08);
}
.update-badge.danger {
  color: #fca5a5;
  border-color: rgba(252,165,165,.35);
  background: rgba(252,165,165,.08);
}
.update-badge.ok {
  color: #86efac;
  border-color: rgba(134,239,172,.35);
  background: rgba(134,239,172,.08);
}
</style>

<style>
/* 右键菜单 — 全局样式 */
.ctx-menu {
  position: fixed; z-index: 9999;
  background: var(--surface, #1e1e2e); border: 1px solid var(--hairline, #333);
  border-radius: 8px; padding: 4px; min-width: 140px;
  box-shadow: 0 8px 32px rgba(0,0,0,.5);
}
.ctx-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-radius: 6px; font-size: 13px; cursor: pointer; color: var(--text, #e0e0e0);
  transition: background .15s;
}
.ctx-item:hover { background: var(--surface-hover, rgba(255,255,255,.08)); }
.ctx-item.danger { color: #f87171; }
.ctx-item.danger:hover { background: rgba(248,113,113,.12); }
.ctx-item.disabled { opacity: .45; cursor: not-allowed; }
.ctx-item.disabled:hover { background: transparent; }
.ctx-icon { font-size: 14px; }

/* 弹窗 */
.modal-mask {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: var(--surface, #1e1e2e); border: 1px solid var(--hairline, #333);
  border-radius: 12px; padding: 24px; min-width: 320px; max-width: 400px;
  box-shadow: 0 16px 48px rgba(0,0,0,.5);
}
.modal-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
.modal-desc { font-size: 13px; color: var(--muted, #888); margin-bottom: 16px; line-height: 1.6; }
.modal-input {
  width: 100%; padding: 10px 12px; border-radius: 8px;
  background: var(--bg, #111); border: 1px solid var(--hairline, #333);
  color: var(--text, #e0e0e0); font-size: 14px; outline: none;
  box-sizing: border-box;
}
.modal-input:focus { border-color: var(--accent, #f66); }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.btn {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--hairline, #333);
  background: var(--surface, #1e1e2e); color: var(--text, #e0e0e0);
  font-size: 13px; cursor: pointer; transition: all .15s;
}
.btn:hover { background: var(--surface-hover, rgba(255,255,255,.08)); }
.btn.primary { background: var(--accent, #f66); color: #fff; border-color: transparent; }
.btn.primary:hover { opacity: .9; }
.btn.danger { background: #dc2626; color: #fff; border-color: transparent; }
.btn.danger:hover { background: #b91c1c; }
</style>
