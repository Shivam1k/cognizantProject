import InlineProductCard from './InlineProductCard'

const chatTextWithoutSourceLinks = content => String(content || '')
  .split('\n')
  .filter(line => !/^\s*source:\s*https?:\/\//i.test(line))
  .join('\n')
  .replace(/https?:\/\/\S+/gi, '')
  .replace(/[ \t]+\n/g, '\n')
  .trim()

/** Render one user or assistant chat bubble with compact category evidence. */
export default function MessageBubble({ role, content, products = [], reasoningDepth }) {
  const user = role === 'user'
  const visibleContent = user ? content : chatTextWithoutSourceLinks(content)
  return <div className={`flex ${user ? 'justify-end' : 'justify-start'}`}>
    <div className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${user ? 'rounded-br-sm bg-gradient-to-br from-indigo-600 to-indigo-700 text-white shadow-indigo-200' : 'rounded-bl-sm border border-slate-100 bg-white text-slate-700 shadow-[0_5px_16px_rgba(30,41,59,.06)]'}`}><p>{visibleContent}</p>{!user && reasoningDepth && <details className="mt-3 rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-900"><summary className="cursor-pointer font-bold">Why this direction</summary><p className="mt-1 whitespace-normal leading-5">{reasoningDepth}</p></details>}{!user && products.slice(0, 2).map((product, index) => <InlineProductCard key={`${product.name}-${index}`} product={product} />)}</div>
  </div>
}
