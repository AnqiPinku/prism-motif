import { invoke } from '@tauri-apps/api/core'

export const inTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

type GatewaySession = {
  baseUrl: string
  token: string
  instanceId: string
}

let sessionPromise: Promise<GatewaySession> | null = null

function browserSession(): GatewaySession {
  return {
    baseUrl: '',
    token: import.meta.env?.VITE_PRISM_SESSION_TOKEN || '',
    instanceId: 'browser-dev',
  }
}

export function getGatewaySession(): Promise<GatewaySession> {
  if (!sessionPromise) {
    sessionPromise = inTauri
      ? invoke<GatewaySession>('gateway_session')
      : Promise.resolve(browserSession())
  }
  return sessionPromise
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const session = await getGatewaySession()
  const headers = new Headers(init.headers)
  if (session.token) headers.set('X-Prism-Session', session.token)
  return fetch(session.baseUrl + path, { ...init, headers })
}
