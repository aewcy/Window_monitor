<script setup>
import { useThemeStore } from '../stores/theme'
const theme = useThemeStore()

const accents = [
  { name: 'coral', color: '#FF6363', label: 'Coral' },
  { name: 'blue', color: '#3B82F6', label: 'Electric Blue' },
  { name: 'amber', color: '#F59E0B', label: 'Amber' },
  { name: 'violet', color: '#8B5CF6', label: 'Violet' },
  { name: 'emerald', color: '#10B981', label: 'Emerald' },
  { name: 'cyan', color: '#06B6D4', label: 'Cyan' },
]
const bgs = [
  { name: 'charcoal', color: '#0F0F11', label: 'Charcoal' },
  { name: 'navy', color: '#0A0E1A', label: 'Deep Navy' },
  { name: 'black', color: '#000000', label: 'Pure Black' },
  { name: 'slate', color: '#1E293B', label: 'Slate' },
  { name: 'warm', color: '#171412', label: 'Warm Dark' },
]
</script>

<template>
  <div class="theme-picker">
    <div class="theme-panel" :class="{ open: theme.panelOpen }">
      <span class="label">强调色</span>
      <button v-for="a in accents" :key="a.name"
        class="option" :class="{ active: theme.accent === a.name }"
        @click="theme.setAccent(a.name)">
        <span class="swatch" :style="{ background: a.color }"></span>
        <span>{{ a.label }}</span>
      </button>
      <div class="divider"></div>
      <span class="label">背景色</span>
      <button v-for="b in bgs" :key="b.name"
        class="option" :class="{ active: theme.bg === b.name }"
        @click="theme.setBg(b.name)">
        <span class="swatch" :style="{ background: b.color }"></span>
        <span>{{ b.label }}</span>
      </button>
    </div>
    <button class="toggle" @click="theme.togglePanel()" title="配色方案">🎨</button>
  </div>
</template>

<style scoped>
.theme-picker { position: fixed; bottom: 52px; right: 20px; z-index: 100; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
.toggle {
  width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--hairline);
  background: var(--surface); backdrop-filter: blur(12px); cursor: pointer;
  display: flex; align-items: center; justify-content: center; font-size: 14px;
  transition: all .2s; box-shadow: var(--shadow-card);
}
.toggle:hover { border-color: var(--accent); transform: scale(1.1); }
.theme-panel {
  background: rgba(15,15,17,0.92); border: 1px solid var(--hairline);
  border-radius: var(--radius-md); padding: 12px; backdrop-filter: blur(20px);
  box-shadow: var(--shadow-lift); display: none; flex-direction: column; gap: 6px; min-width: 140px;
}
.theme-panel.open { display: flex; }
.label { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 4px; }
.divider { border-top: 1px solid var(--hairline); margin: 6px 0; }
.option {
  display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 6px;
  cursor: pointer; transition: background .1s; font-size: 11px; color: var(--text-secondary);
  border: none; background: transparent; font-family: inherit; width: 100%; text-align: left;
}
.option:hover { background: var(--surface-hover); }
.option.active { background: var(--surface-hover); color: var(--text); }
.swatch { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; border: 2px solid transparent; transition: border-color .15s; }
.option.active .swatch { border-color: var(--text); }
</style>
