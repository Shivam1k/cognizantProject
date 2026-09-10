import { useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { recommendProducts } from '../../api'

const scoreBar = (label, value) => (
  <div className="flex items-center gap-2 text-xs" key={label}>
    <span className="w-28 shrink-0 text-slate-500">{label}</span>
    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#e8684c]" style={{ width: `${Math.round((value || 0) * 100)}%` }} /></div>
    <span className="w-10 shrink-0 text-right font-semibold text-slate-700">{Math.round((value || 0) * 100)}%</span>
  </div>
)

/** On-demand hybrid recommendation: deep-scrapes the shortlist (reviews + Q&A),
 *  runs the deterministic rule-based scorer, then shows the LLM's justification
 *  for the ranking it was given — never a ranking the LLM invented itself.
 *  Deliberately not run automatically: deep scraping is comparatively slow,
 *  so it only runs when the user asks for it on the current shortlist. */
export default function WhyThisPick({ sessionId, products, onResult, onAnalysisStateChange }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setLoading(true)
    setError('')
    onAnalysisStateChange?.({ status: 'loading' })
    try {
      const { data } = await recommendProducts(sessionId, products.slice(0, 12), '')
      setResult(data)
      onResult?.(data)
      onAnalysisStateChange?.({ status: 'complete' })
    } catch (e) {
      const message = e.response?.data?.detail || 'Could not run the deep comparison. Please try again.'
      setError(message)
      onAnalysisStateChange?.({ status: 'error', error: message })
    } finally {
      setLoading(false)
    }
  }

  if (products.length < 2) return null

  return <section className="overflow-hidden rounded-3xl border border-indigo-100 bg-gradient-to-br from-indigo-50 via-white to-teal-50/50 p-5 shadow-[0_14px_34px_rgba(79,70,229,.08)] sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-200"><Sparkles size={17} /></span><div><h2 className="font-bold text-slate-800">AI recommendation</h2><p className="text-xs text-slate-500">Deep comparison for your shortlist</p></div></div>
      <button onClick={run} disabled={loading} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-md shadow-indigo-200 transition hover:bg-indigo-700 disabled:opacity-60">
        {loading ? <><Loader2 size={14} className="animate-spin" />Deep-scraping {Math.min(products.length, 12)} products…</> : (result ? 'Re-run deep comparison' : 'Get recommendation')}
      </button>
    </div>
    <p className="mt-2 text-xs text-slate-500">Scrapes reviews and Q&amp;A for the {Math.min(products.length, 12)} products currently in scope, scores them on price, rating, review sentiment and feature match, then explains the pick. This can take a little while — nothing else in the app is blocked while it runs.</p>
    {error && <p className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
    {result && <div className="mt-5 space-y-4">
      <p className="rounded-xl bg-amber-50 p-4 text-sm font-semibold text-slate-800">{result.summary}</p>
      <div className="space-y-3">
        {result.items.map(item => <div key={item.product_key} className={`rounded-xl border p-4 ${item.rank === 1 ? 'border-amber-300 bg-amber-50/40' : 'border-slate-200'}`}>
          <div className="flex items-center justify-between gap-3"><span className="text-sm font-bold text-slate-800">#{item.rank} · {item.name}</span><span className="text-xs font-semibold text-slate-500">Score {Math.round(item.score_breakdown.total_score * 100)}</span></div>
          {item.justification && <p className="mt-1 text-xs text-slate-600">{item.justification}</p>}
          <div className="mt-3 space-y-1.5">
            {scoreBar('Price', item.score_breakdown.price_score)}
            {scoreBar('Rating', item.score_breakdown.rating_score)}
            {scoreBar('Review sentiment', item.score_breakdown.review_sentiment_score)}
            {scoreBar('Feature match', item.score_breakdown.feature_match_score)}
          </div>
        </div>)}
      </div>
    </div>}
  </section>
}
