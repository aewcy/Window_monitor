<script setup>
import { computed, onMounted, ref } from 'vue'
import { useScreenshotStore } from '../stores/screenshot'
import * as api from '../api'

const ss = useScreenshotStore()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const rules = ref([])
const warmupSeconds = ref(10)
const keepaliveSeconds = ref(300)
const formType = ref('process')
const formPattern = ref('')

const processPlaceholder = '例如：wechat.exe'
const urlPlaceholder = '例如：youtube.com/watch'

const panelTitle = computed(() =>
  `特殊名单：前 ${warmupSeconds.value} 秒正常保存，之后每 ${Math.round(keepaliveSeconds.value / 60)} 分钟补 1 张`
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getScreenshotRules()
    rules.value = data.items || []
    warmupSeconds.value = data.warmup_seconds || 10
    keepaliveSeconds.value = data.keepalive_seconds || 300
  } catch (err) {
    error.value = '名单加载失败'
  } finally {
    loading.value = false
  }
}

async function addRule() {
  const pattern = formPattern.value.trim()
  if (!pattern || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const data = await api.createScreenshotRule(formType.value, pattern, true)
    rules.value = [data.item, ...rules.value]
    formPattern.value = ''
  } catch (err) {
    error.value = '新增规则失败'
  } finally {
    saving.value = false
  }
}

async function toggleRule(rule) {
  const targetEnabled = !rule.enabled
  rule.enabled = targetEnabled
  try {
    const data = await api.updateScreenshotRule(rule.id, { enabled: targetEnabled })
    Object.assign(rule, data.item)
  } catch (err) {
    rule.enabled = !targetEnabled
    error.value = '更新规则失败'
  }
}

async function removeRule(rule) {
  const snapshot = [...rules.value]
  rules.value = rules.value.filter(item => item.id !== rule.id)
  try {
    await api.deleteScreenshotRule(rule.id)
  } catch (err) {
    rules.value = snapshot
    error.value = '删除规则失败'
  }
}

function close() {
  ss.rulesPanelOpen = false
}

onMounted(load)
</script>

<template>
  <div class="rule-overlay" :class="{ open: ss.rulesPanelOpen }" @click.self="close">
    <div class="rule-box">
      <div class="rule-head">
        <div>
          <div class="eyebrow">历史截图特殊名单</div>
          <div class="title">{{ panelTitle }}</div>
        </div>
        <button class="close-btn" @click="close">关闭</button>
      </div>

      <div class="rule-form">
        <select v-model="formType" class="field kind">
          <option value="process">程序名</option>
          <option value="url_contains">网页 URL 模糊匹配</option>
        </select>
        <input
          v-model="formPattern"
          class="field pattern"
          :placeholder="formType === 'process' ? processPlaceholder : urlPlaceholder"
          @keydown.enter.prevent="addRule">
        <button class="add-btn" :disabled="saving || !formPattern.trim()" @click="addRule">加入名单</button>
      </div>

      <div class="rule-tip">
        非名单对象继续按原策略保存。名单对象切到前台后的前 10 秒照常保存，之后只保留前台会话补帧。
      </div>

      <div v-if="error" class="rule-error">{{ error }}</div>
      <div v-if="loading" class="rule-empty">加载中...</div>
      <div v-else-if="!rules.length" class="rule-empty">还没有特殊名单</div>

      <div v-else class="rule-list">
        <div v-for="rule in rules" :key="rule.id" class="rule-item" :class="{ disabled: !rule.enabled }">
          <div class="rule-meta">
            <span class="rule-kind">{{ rule.rule_type === 'process' ? '程序' : '网页' }}</span>
            <span class="rule-pattern">{{ rule.pattern }}</span>
          </div>
          <div class="rule-actions">
            <button class="ghost-btn" @click="toggleRule(rule)">{{ rule.enabled ? '停用' : '启用' }}</button>
            <button class="ghost-btn danger" @click="removeRule(rule)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-overlay {
  position: fixed; inset: 0; z-index: 220;
  display: flex; align-items: center; justify-content: center;
  background: rgba(5, 6, 10, 0.45);
  backdrop-filter: blur(14px);
  opacity: 0;
  pointer-events: none;
  transition: opacity .18s ease;
}
.rule-overlay.open { opacity: 1; pointer-events: auto; }
.rule-box {
  width: min(900px, calc(100vw - 40px));
  max-height: min(760px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(19,21,28,.96), rgba(11,12,16,.98));
  box-shadow: var(--shadow-lift);
  padding: 20px;
}
.rule-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 18px;
}
.eyebrow {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: .08em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}
.title { margin-top: 6px; font-size: 18px; color: var(--text); }
.close-btn,
.add-btn,
.ghost-btn {
  border: 1px solid var(--hairline);
  background: var(--surface);
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 8px 14px;
  cursor: pointer;
}
.close-btn:hover,
.add-btn:hover,
.ghost-btn:hover {
  color: var(--text);
  border-color: var(--accent);
  background: var(--surface-hover);
}
.add-btn:disabled { opacity: .5; cursor: not-allowed; }
.rule-form {
  display: grid;
  grid-template-columns: 180px 1fr 128px;
  gap: 12px;
  margin-bottom: 12px;
}
.field {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: rgba(255,255,255,.05);
  color: var(--text);
  padding: 11px 12px;
}
.rule-tip,
.rule-error,
.rule-empty {
  border-radius: var(--radius-md);
  padding: 12px 14px;
  margin-bottom: 12px;
}
.rule-tip {
  background: rgba(96,165,250,.08);
  color: var(--text-secondary);
}
.rule-error {
  background: rgba(242,54,69,.14);
  color: #ffd2d7;
}
.rule-empty {
  background: rgba(255,255,255,.04);
  color: var(--muted);
}
.rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rule-item {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--hairline);
  background: rgba(255,255,255,.04);
  border-radius: var(--radius-md);
  padding: 14px;
}
.rule-item.disabled { opacity: .6; }
.rule-meta {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.rule-kind {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--accent);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 999px;
  padding: 4px 8px;
}
.rule-pattern {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  color: var(--text);
}
.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ghost-btn.danger:hover {
  border-color: var(--red);
  color: #ffd2d7;
}
@media (max-width: 760px) {
  .rule-form {
    grid-template-columns: 1fr;
  }
  .rule-item {
    flex-direction: column;
    align-items: flex-start;
  }
  .rule-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
