import axios from 'axios'

const client = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000' })

/** Create the browser's persistent assistant session. */
export const createSession = () => client.post('/session')
/** Submit a natural-language product request. */
export const sendChat = (session_id, message, selected_products = []) => client.post('/chat', { session_id, message, selected_products })
/** Upload an image for vision identification. */
export const uploadPhoto = (session_id, file) => {
  const form = new FormData(); form.append('file', file)
  return client.post(`/upload-photo?session_id=${encodeURIComponent(session_id)}`, form)
}
/** Upload a PDF spec sheet. */
export const uploadPdf = (session_id, file) => {
  const form = new FormData(); form.append('file', file)
  return client.post(`/upload-pdf?session_id=${encodeURIComponent(session_id)}`, form)
}
/** Load persisted session messages for the session timeline. */
export const getHistory = sessionId => client.get(`/history/${encodeURIComponent(sessionId)}`)
/** Deep-scrape a shortlist (reviews + Q&A) and get a scored, justified recommendation. */
export const recommendProducts = (session_id, products, user_query = '', priorities = {}) =>
  client.post('/recommend', { session_id, products, user_query, priorities }, { timeout: 60000 })
