export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark'
}

export function getThemeFromDom(): Theme | null {
  const t = document.documentElement.dataset.theme
  return isTheme(t) ? t : null
}

export function getStoredTheme(): Theme | null {
  try {
    const t = localStorage.getItem(STORAGE_KEY)
    return isTheme(t) ? t : null
  } catch {
    return null
  }
}

export function getSystemTheme(): Theme {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(theme: Theme, opts?: { persist?: boolean }) {
  document.documentElement.dataset.theme = theme

  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#0b1020' : '#f6f8ff')

  if (opts?.persist) {
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // ignore
    }
  }
}

