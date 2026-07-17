<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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
const typeMenuOpen = ref(false)
const typePicker = ref(null)

const ruleTypes = [
  { value: 'process', label: '程序名', hint: '按 exe 文件名匹配' },
  { value: 'url_contains', label: '网页 URL', hint: '按网址连续匹配' },
]

const processPlaceholder = '例如：wechat.exe'
const urlPlaceholder = '例如：youtube.com/watch'

const panelTitle = computed(() =>
  `特殊名单：前 ${warmupSeconds.value} 秒正常保存，之后每 ${Math.round(keepaliveSeconds.value / 60)} 分钟补 1 张`
)
const selectedRuleType = computed(() => ruleTypes.find(item => item.value === formType.value) || ruleTypes[0])

function toggleTypeMenu() {
  typeMenuOpen.value = !typeMenuOpen.value
}

function selectRuleType(value) {
  formType.value = value
  typeMenuOpen.value = false
}

function closeTypeMenuOnOutsideClick(event) {
  if (typePicker.value && !typePicker.value.contains(event.target)) {
    typeMenuOpen.value = false
  }
}

function closeTypeMenuOnEscape(event) {
  if (event.key === 'Escape') typeMenuOpen.value = false
}

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

onMounted(() => {
  load()
  document.addEventListener('pointerdown', closeTypeMenuOnOutsideClick)
  document.addEventListener('keydown', closeTypeMenuOnEscape)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeTypeMenuOnOutsideClick)
  document.removeEventListener('keydown', closeTypeMenuOnEscape)
})
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
        <div ref="typePicker" class="type-picker" :class="{ open: typeMenuOpen }">
          <button
            type="button"
            class="field type-trigger"
            :aria-expanded="typeMenuOpen"
            aria-haspopup="listbox"
            @click="toggleTypeMenu"
            @keydown.down.prevent="typeMenuOpen = true">
            <span class="type-trigger-label">{{ selectedRuleType.label }}</span>
            <span class="type-trigger-chevron" aria-hidden="true"></span>
          </button>
          <div v-if="typeMenuOpen" class="type-menu" role="listbox" aria-label="特殊名单类型">
            <button
              v-for="type in ruleTypes"
              :key="type.value"
              type="button"
              class="type-option"
              :class="{ selected: formType === type.value }"
              role="option"
              :aria-selected="formType === type.value"
              @click="selectRuleType(type.value)">
              <span class="type-option-icon" aria-hidden="true">{{ type.value === 'process' ? '▣' : '⌁' }}</span>
              <span>
                <span class="type-option-label">{{ type.label }}</span>
                <span class="type-option-hint">{{ type.hint }}</span>
              </span>
              <span v-if="formType === type.value" class="type-option-check" aria-hidden="true">✓</span>
            </button>
          </div>
        </div>
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
.type-picker {
  position: relative;
  min-width: 0;
}
.type-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
  cursor: pointer;
}
.type-trigger:hover,
.type-picker.open .type-trigger {
  border-color: rgba(96,165,250,.72);
  background: rgba(96,165,250,.09);
}
.type-trigger:focus-visible,
.type-option:focus-visible {
  outline: 2px solid rgba(96,165,250,.8);
  outline-offset: 2px;
}
.type-trigger-label { color: var(--text); }
.type-trigger-chevron {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-right: 1.5px solid var(--text-secondary);
  border-bottom: 1.5px solid var(--text-secondary);
  transform: rotate(45deg) translateY(-2px);
  transition: transform .16s ease, border-color .16s ease;
}
.type-picker.open .type-trigger-chevron {
  border-color: var(--accent);
  transform: rotate(225deg) translate(-2px, -1px);
}
.type-menu {
  position: absolute;
  z-index: 8;
  top: calc(100% + 8px);
  left: 0;
  width: max(250px, 100%);
  padding: 6px;
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(29,32,42,.99), rgba(15,17,23,.99));
  box-shadow: 0 18px 42px rgba(0,0,0,.42);
}
.type-option {
  width: 100%;
  display: grid;
  grid-template-columns: 24px 1fr 18px;
  align-items: center;
  gap: 9px;
  padding: 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}
.type-option:hover,
.type-option.selected {
  background: rgba(96,165,250,.12);
  color: var(--text);
}
.type-option-icon {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid rgba(96,165,250,.28);
  border-radius: 7px;
  color: var(--accent);
  font-size: 13px;
}
.type-option-label,
.type-option-hint {
  display: block;
}
.type-option-label { font-size: 13px; }
.type-option-hint {
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
}
.type-option-check {
  color: var(--accent);
  font-size: 14px;
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
