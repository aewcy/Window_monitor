<script setup>
import { useConfirm } from '../composables/useConfirm'
const { visible, message, onConfirm, onCancel } = useConfirm()
</script>

<template>
  <div class="confirm-overlay" :class="{ open: visible }" @click.self="onCancel">
    <div class="confirm-box">
      <p>{{ message }}</p>
      <div class="confirm-actions">
        <button class="btn-cancel" @click="onCancel">取消</button>
        <button class="btn-danger" @click="onConfirm">删除</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.confirm-overlay {
  position: fixed; inset: 0; z-index: 300;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(8px);
  opacity: 0; pointer-events: none; transition: opacity .2s;
}
.confirm-overlay.open { opacity: 1; pointer-events: auto; }
.confirm-box {
  background: rgba(15,15,17,0.95); border: 1px solid var(--hairline);
  border-radius: var(--radius-md); padding: 24px; max-width: 360px;
  text-align: center; box-shadow: var(--shadow-lift);
}
.confirm-box p { margin-bottom: 16px; font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.confirm-actions { display: flex; gap: 8px; justify-content: center; }
.btn-cancel, .btn-danger {
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  padding: 6px 16px; border-radius: 6px; cursor: pointer; transition: all .15s;
}
.btn-cancel { border: 1px solid var(--hairline); background: var(--surface); color: var(--text-secondary); }
.btn-cancel:hover { border-color: var(--text-secondary); color: var(--text); }
.btn-danger { border: 1px solid rgba(242,54,69,.3); background: rgba(242,54,69,.1); color: var(--red); }
.btn-danger:hover { background: rgba(242,54,69,.2); border-color: var(--red); }
</style>
