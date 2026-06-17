import { ref } from 'vue'

const visible = ref(false)
const message = ref('')
let resolveFn = null

export function useConfirm() {
  function confirm(msg) {
    message.value = msg
    visible.value = true
    return new Promise(resolve => { resolveFn = resolve })
  }

  function onConfirm() {
    visible.value = false
    if (resolveFn) resolveFn(true)
    resolveFn = null
  }

  function onCancel() {
    visible.value = false
    if (resolveFn) resolveFn(false)
    resolveFn = null
  }

  return { visible, message, confirm, onConfirm, onCancel }
}
