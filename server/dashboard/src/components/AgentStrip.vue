<script setup>
import { useAgentStore } from '../stores/agent'
const agent = useAgentStore()
</script>

<template>
  <div class="agent-strip">
    <div v-for="a in agent.agents" :key="a.name"
      class="agent-pill" :class="{ active: agent.selectedAgent === a.name }"
      @click="agent.selectAgent(a.name)">
      <span class="dot" :class="a.status === 'online' ? 'online' : 'offline'"></span>
      <span class="name">{{ a.display_name || a.name }}</span>
      <span class="meta">{{ a.screenshot_interval ? a.screenshot_interval + 's' : (a.status === 'online' ? '在线' : '离线') }}</span>
    </div>
    <div v-if="!agent.agents.length" class="agent-pill" style="opacity:0.5">
      <span class="name">暂无被控端</span>
    </div>
  </div>
</template>

<style scoped>
.agent-strip { display: flex; gap: 10px; padding: 10px 24px 0; overflow-x: auto; position: relative; z-index: 1; }
.agent-pill {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-md);
  cursor: pointer; transition: all .2s cubic-bezier(0.22,1,0.36,1); white-space: nowrap; flex-shrink: 0;
}
.agent-pill:hover { background: var(--surface-hover); transform: translateY(-2px); box-shadow: var(--shadow-card); }
.agent-pill.active { border-color: var(--accent); background: rgba(255,99,99,.08); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.online { background: var(--green); box-shadow: 0 0 6px rgba(74,222,128,.4); }
.dot.offline { background: var(--muted); }
.name { font-size: 12px; font-weight: 600; }
.meta { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
</style>
