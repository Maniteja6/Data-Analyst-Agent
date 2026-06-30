import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// Inject correlation ID
apiClient.interceptors.request.use((config) => {
  config.headers['X-Correlation-ID'] =
    `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return config
})

// Normalise errors
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.error ?? err.message ?? 'An unexpected error occurred.'
    return Promise.reject(new Error(message))
  },
)