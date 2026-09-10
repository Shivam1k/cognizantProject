import { Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ChatPanel from '../components/ChatPanel'
import ComparisonTable from '../components/ComparisonTable'
import ProductCard from '../components/ProductCard'
import SkeletonCard from '../components/SkeletonCard'
import ViewToggle from '../components/ViewToggle'

const productKey = product => `${product.name}|${product.price}|${product.source}|${product.link}`

export default function ChatPage({ messages, products, selectedProducts, loading, connecting, error, onSend, onPhoto, onPdf, onToggleComparison, onNewChat, sessionId }) {
  const [view, setView] = useState('cards')
  const cardRefs = useRef({})
  const selected = product => selectedProducts.some(item => item.name === product.name && item.price === product.price && item.source === product.source && item.link === product.link)
  const comparisonProducts = selectedProducts.length ? selectedProducts : products

  // The latest assistant reply already carries exactly the products it's
  // talking about (see App.jsx). Use that to ring + scroll to those cards
  // in the right panel without hiding anything else from view.
  const lastAssistant = [...messages].reverse().find(message => message.role === 'assistant')
  const mentionedKeys = new Set((lastAssistant?.products || []).map(productKey))

  useEffect(() => {
    if (!mentionedKeys.size) return
    const firstKey = [...mentionedKeys][0]
    const node = cardRefs.current[firstKey]
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastAssistant])

  return <main className="mx-auto max-w-7xl px-4 py-7 sm:px-6 lg:py-10"><div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-bold uppercase tracking-[.15em] text-indigo-600">Research workspace</p><h1 className="mt-1 text-4xl font-black tracking-tight text-[#182230] sm:text-5xl">Continuous product research</h1><p className="mt-3 text-sm leading-6 text-[#68717d]">Ask follow-up questions or search another product in this same conversation.</p></div><button onClick={onNewChat} disabled={connecting} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-[#182230] shadow-sm hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"><Plus size={16} />New chat</button></div>
    <div className="grid gap-6 lg:grid-cols-[minmax(0,.9fr)_minmax(0,1.1fr)]">
      <ChatPanel messages={messages} loading={loading || connecting} ready={Boolean(sessionId)} onSend={onSend} onPhoto={onPhoto} onPdf={onPdf} />
      <section className="min-h-[620px] rounded-[1.25rem] border border-[#e5e0d7] bg-white p-5 shadow-[0_14px_40px_rgba(24,34,48,.06)] sm:p-6"><div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid h-12 w-12 place-items-center overflow-hidden rounded-xl bg-[#f7c96d] shadow-sm"><img src="/productgenie-character.avif" alt="" className="h-full w-full object-contain" /></span><div><h2 className="font-bold text-[#182230]">Current results</h2><p className="text-xs text-[#68717d]">{products.length ? `${products.length} products in the latest search${selectedProducts.length ? ` · ${selectedProducts.length} selected for comparison` : ''}` : 'Your latest product results will appear here'}</p></div></div><ViewToggle view={view} onChange={setView} /></div>
        {error && <p className="mb-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
        {loading && !products.length && <div className="grid gap-4 sm:grid-cols-2">{[1, 2, 3, 4].map(item => <SkeletonCard key={item} />)}</div>}
        {!loading && !products.length && <div className="grid min-h-80 place-items-center rounded-2xl border border-dashed border-[#d8d1c6] bg-[#f8f6f1] p-8 text-center"><div><span className="mx-auto mb-3 grid h-16 w-16 place-items-center overflow-hidden rounded-2xl bg-[#f7c96d] shadow-sm"><img src="/productgenie-character.avif" alt="" className="h-full w-full object-contain" /></span><p className="font-semibold text-[#182230]">Your product results will show up here</p><p className="mt-2 max-w-xs text-sm text-[#68717d]">Ask about a product, upload a product photo, or add a PDF spec sheet to get started.</p></div></div>}
        {!!products.length && view === 'cards' && <div className="grid gap-4 sm:grid-cols-2">{products.slice(0, 12).map((product, index) => {
          const key = productKey(product)
          return <ProductCard
            key={`${product.name}-${index}`}
            ref={node => { cardRefs.current[key] = node }}
            product={product}
            detailsPath={`/product/${index}`}
            selected={selected(product)}
            onToggleComparison={onToggleComparison}
            highlighted={mentionedKeys.has(key)}
          />
        })}</div>}
        {!!products.length && view === 'table' && <ComparisonTable products={comparisonProducts} />}
      </section>
    </div>
  </main>
}
