import { useEffect, useMemo, useRef, useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { createSession, sendChat, uploadPdf, uploadPhoto } from './api'
import Navbar from './components/Navbar'
import AnalyticsPage from './pages/AnalyticsPage'
import ChatPage from './pages/ChatPage'
import LandingPage from './pages/LandingPage'
import ProductDetailsPage from './pages/ProductDetailsPage'

const productKey = product => `${product.name}|${product.price}|${product.source}|${product.link}`
const welcome = { role: 'assistant', content: 'Hi, I’m ProductGenie. Ask about any product, then continue with follow-up questions or search another product whenever you like.' }

/** Own one continuous product-research session across the app's routes. */
export default function App() {
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState([welcome])
  const [products, setProducts] = useState([])
  const [selectedProducts, setSelectedProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [connecting, setConnecting] = useState(true)
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('productgenie-theme') === 'dark')
  const sessionEpoch = useRef(0)

  useEffect(() => { localStorage.setItem('productgenie-theme', darkMode ? 'dark' : 'light') }, [darkMode])

  const startNewChat = async () => {
    sessionEpoch.current += 1
    setSessionId('')
    setMessages([welcome])
    setProducts([])
    setSelectedProducts([])
    setError('')
    setLoading(false)
    setConnecting(true)
    try {
      const { data } = await createSession()
      setSessionId(data.session_id)
    } catch {
      setError('Could not create a new ProductGenie session. Start the backend on port 8000 and try again.')
    } finally {
      setConnecting(false)
    }
  }

  useEffect(() => { startNewChat() }, [])

  const run = async (action, optimistic) => {
    if (!sessionId) {
      setError('The chat session is not ready. Refresh the page after the API starts.')
      return
    }
    const requestEpoch = sessionEpoch.current
    setError('')
    setLoading(true)
    if (optimistic) setMessages(items => [...items, optimistic])
    try {
      const { data } = await action()
      if (requestEpoch !== sessionEpoch.current) return
      const responseProducts = data.products || []
      if (responseProducts.length) setProducts(responseProducts.slice(0, 12))
      setMessages(items => [...items, { role: 'assistant', content: data.response, products: responseProducts.slice(0, 12), reasoningDepth: data.reasoning_depth || '', recommendation: data.recommendation || null }])
    } catch (e) {
      if (requestEpoch !== sessionEpoch.current) return
      const detail = e.response?.data?.detail || 'The request could not be completed. Please try again.'
      setError(detail)
      setMessages(items => [...items, { role: 'assistant', content: `I couldn't complete that request: ${detail}` }])
    } finally {
      if (requestEpoch === sessionEpoch.current) setLoading(false)
    }
  }

  const toggleComparison = product => setSelectedProducts(current => {
    const selected = current.some(item => productKey(item) === productKey(product))
    return selected ? current.filter(item => productKey(item) !== productKey(product)) : [...current, product]
  })

  const mergeDeepProducts = deepProducts => {
    if (!Array.isArray(deepProducts) || !deepProducts.length) return
    const merge = current => current.map(product => deepProducts.find(item => productKey(item) === productKey(product)) || product)
    setProducts(merge)
    setSelectedProducts(merge)
  }

  const shared = useMemo(() => ({
    sessionId, messages, products, selectedProducts, loading, connecting, error,
    onSend: text => run(() => sendChat(sessionId, text, selectedProducts), { role: 'user', content: text }),
    onPhoto: file => run(() => uploadPhoto(sessionId, file), { role: 'user', content: `Uploaded photo: ${file.name}` }),
    onPdf: file => run(() => uploadPdf(sessionId, file), { role: 'user', content: `Uploaded PDF: ${file.name}` }),
    onToggleComparison: toggleComparison,
    onNewChat: startNewChat, onDeepProducts: mergeDeepProducts,
  }), [sessionId, messages, products, selectedProducts, loading, connecting, error])

  return <BrowserRouter><div className={`min-h-screen text-slate-800 ${darkMode ? 'dark-theme' : ''}`}><Navbar onNewChat={startNewChat} darkMode={darkMode} onToggleTheme={() => setDarkMode(value => !value)} /><Routes>
    <Route path="/" element={<LandingPage />} /><Route path="/chat" element={<ChatPage {...shared} />} />
    <Route path="/analytics" element={<AnalyticsPage {...shared} />} /><Route path="/product/:productIndex" element={<ProductDetailsPage products={products} />} /><Route path="*" element={<LandingPage />} />
  </Routes></div></BrowserRouter>
}
