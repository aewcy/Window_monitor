import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const BACKDROP_COLORS = {
  coral:   ['rgba(255,99,99,0.08)',  'rgba(167,139,250,0.06)', 'rgba(96,165,250,0.05)'],
  blue:    ['rgba(59,130,246,0.08)',  'rgba(96,165,250,0.06)', 'rgba(34,211,238,0.05)'],
  amber:   ['rgba(245,158,11,0.08)', 'rgba(251,191,36,0.06)', 'rgba(255,99,99,0.05)'],
  violet:  ['rgba(139,92,246,0.08)', 'rgba(167,139,250,0.06)', 'rgba(236,72,153,0.05)'],
  emerald: ['rgba(16,185,129,0.08)', 'rgba(74,222,128,0.06)', 'rgba(34,211,238,0.05)'],
  cyan:    ['rgba(6,182,212,0.08)',  'rgba(34,211,238,0.06)', 'rgba(96,165,250,0.05)'],
}

export const useThemeStore = defineStore('theme', () => {
  const accent = ref(localStorage.getItem('accent') || 'coral')
  const bg = ref(localStorage.getItem('bg') || 'charcoal')
  const panelOpen = ref(false)

  function setAccent(name) {
    accent.value = name
    document.documentElement.setAttribute('data-accent', name)
    localStorage.setItem('accent', name)
    updateBackdrop(name)
  }

  function setBg(name) {
    bg.value = name
    document.documentElement.setAttribute('data-bg', name)
    localStorage.setItem('bg', name)
  }

  function updateBackdrop(name) {
    const c = BACKDROP_COLORS[name] || BACKDROP_COLORS.coral
    const el = document.querySelector('.backdrop')
    if (el) {
      el.style.background =
        `radial-gradient(ellipse at 30% 50%, ${c[0]} 0%, transparent 50%),
         radial-gradient(ellipse at 70% 30%, ${c[1]} 0%, transparent 50%),
         radial-gradient(ellipse at 50% 80%, ${c[2]} 0%, transparent 50%)`
    }
  }

  function togglePanel() { panelOpen.value = !panelOpen.value }
  function closePanel() { panelOpen.value = false }

  // Init on load
  function init() {
    document.documentElement.setAttribute('data-accent', accent.value)
    document.documentElement.setAttribute('data-bg', bg.value)
    updateBackdrop(accent.value)
  }

  return { accent, bg, panelOpen, setAccent, setBg, togglePanel, closePanel, init }
})
