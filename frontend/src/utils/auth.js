/**
 * Token and user info management utilities.
 * Uses localStorage for persistence across page reloads.
 */

const TOKEN_KEY = 'dingtalk_leave_token'
const USER_KEY = 'dingtalk_leave_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function removeUser() {
  localStorage.removeItem(USER_KEY)
}

/**
 * Check if running inside DingTalk app (by User-Agent).
 */
export function isInDingTalk() {
  return /DingTalk/i.test(navigator.userAgent)
}
