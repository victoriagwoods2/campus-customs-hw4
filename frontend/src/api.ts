export interface StockOption {
  size: string
  quantity: number
}

export interface Product {
  product_id: string
  name: string
  garment_type: string
  description: string
  colors: string[]
  search_tags: string[]
  image_url: string
  price: number
  sizes?: StockOption[]
}

export interface AuthUser {
  id: number
  first_name: string
  last_name: string
  email: string
}

export interface AccountRegistration {
  first_name: string
  last_name: string
  email: string
  password: string
  password_confirmation: string
}

export interface AccountCredentials {
  email: string
  password: string
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatPageContext {
  page_type: 'home' | 'products' | 'product_detail' | 'about' | 'login' | 'create_account' | 'other'
  path: string
  product_id?: string
}

export interface ProductMatch {
  product_id: string
  name: string
  garment_type: string
  image_url: string
  price: number
  short_description: string
  sizes: StockOption[]
}

export interface ChatReply {
  reply: string
  products: ProductMatch[]
}

export interface SavedChatMessage extends ChatTurn {
  id: number
  created_at: string
  products: ProductMatch[]
}

export interface ChatHistoryResponse {
  authenticated: boolean
  messages: SavedChatMessage[]
}

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { credentials: 'include' })
  if (!response.ok) {
    let message = `The shop service returned ${response.status}.`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the status message if the server did not return JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  if (!response.ok) {
    let message = `The shop service returned ${response.status}.`
    try {
      const body = await response.json() as { detail?: string | Array<{ msg?: string }> }
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg).filter(Boolean).join(' ')
    } catch {
      // Keep the status message if the server did not return JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function getProducts(): Promise<Product[]> {
  return readJson<Product[]>('/api/products')
}

export function getProduct(productId: string): Promise<Product> {
  return readJson<Product>(`/api/products/${encodeURIComponent(productId)}`)
}

export function getCurrentUser(): Promise<AuthUser> {
  return readJson<AuthUser>('/api/auth/me')
}

export function registerAccount(payload: AccountRegistration): Promise<AuthUser> {
  return postJson<AuthUser>('/api/auth/register', payload)
}

export function loginAccount(payload: AccountCredentials): Promise<AuthUser> {
  return postJson<AuthUser>('/api/auth/login', payload)
}

export function logoutAccount(): Promise<{ status: string }> {
  return postJson<{ status: string }>('/api/auth/logout')
}

export function getChatHistory(): Promise<ChatHistoryResponse> {
  return readJson<ChatHistoryResponse>('/api/chat/history')
}

export function sendChatMessage(message: string, history: ChatTurn[], pageContext: ChatPageContext): Promise<ChatReply> {
  return postJson<ChatReply>('/api/chat', {
    message,
    history: history.slice(-12),
    page_context: pageContext,
  })
}

export function getImageUrl(imageUrl: string): string {
  return `${apiBase}${imageUrl}`
}

export function formatPrice(price: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(price)
}
