import { useEffect, useMemo, useState } from 'react'
import { BarChart3, CheckCircle2, Star, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getHistory } from '../api'
import ExportButton from '../components/analytics/ExportButton'
import PriceChart from '../components/analytics/PriceChart'
import SessionTimeline from '../components/analytics/SessionTimeline'
import SpecRadarChart from '../components/analytics/SpecRadarChart'
import SpecBreakdownBars from '../components/analytics/SpecBreakdownBars'
import StatCard from '../components/analytics/StatCard'
import ValueScatterPlot from '../components/analytics/ValueScatterPlot'
import WhyThisPick from '../components/analytics/WhyThisPick'

const priceNumber = price => Number(String(price || '').replace(/[^0-9.]/g, '')) || 0
const shortName = name => name.length > 18 ? `${name.slice(0, 18)}…` : name
const numberFrom = value => {
  const match = String(value ?? '').replace(/,/g, '').match(/\d+(?:\.\d+)?/)
  return match ? Number(match[0]) : null
}
const fieldId = key => key.toLowerCase().replace(/[^a-z0-9]+/g, '')
const productIdentity = product => `${product.name}|${product.price}|${product.source}|${product.link}`

const formatFeatureValue = (fieldKey, value) => {
  if (value == null || value === '') return 'Not listed'
  const text = String(value).trim()
  const normalizedKey = normalizeFeatureKey(fieldKey)
  if (!text) return 'Not listed'

  const cleaned = text
    .replace(/\s*[:;-]\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (normalizedKey === 'ram') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(gb|gib)\b/i, '$1 GB').replace(/\b(\d+(?:\.\d+)?)\s*(mb)\b/i, '$1 MB')
  if (normalizedKey === 'storage') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(gb|tb)\b/i, '$1 $2').replace(/\b(\d+(?:\.\d+)?)\s*(rom|storage)\b/i, '$1 GB').replace(/\b(\d+(?:\.\d+)?)\s*(mb)\b/i, '$1 MB')
  if (normalizedKey === 'battery') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(mah)\b/i, '$1 mAh')
  if (normalizedKey === 'display') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(in|inch|inches)\b/i, '$1 in').replace(/\b(\d+(?:\.\d+)?)\s*(cm)\b/i, '$1 cm')
  if (normalizedKey === 'camera') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(mp|megapixel|megapixels)\b/i, '$1 MP')
  if (normalizedKey === 'weight') return cleaned.replace(/\b(\d+(?:\.\d+)?)\s*(kg)\b/i, '$1 kg').replace(/\b(\d+(?:\.\d+)?)\s*(g)\b/i, '$1 g')
  if (normalizedKey === 'resolution') return cleaned.replace(/\s*[x×]\s*/i, ' × ')
  return cleaned
}

const comparableLabels = {
  ram: 'RAM',
  storage: 'Storage',
  battery: 'Battery',
  display: 'Display',
  camera: 'Camera',
  processor: 'Processor',
  weight: 'Weight',
  os: 'OS',
  network: 'Network',
  resolution: 'Resolution',
}

const normalizeFeatureKey = key => {
  const text = String(key || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
  if (!text) return ''

  const aliases = {
    'internal storage': 'storage',
    'hard disk': 'storage',
    'hard drive': 'storage',
    'disk storage': 'storage',
    'solid state drive': 'storage',
    ssd: 'storage',
    hdd: 'storage',
    storage: 'storage',
    memory: 'ram',
    'system memory': 'ram',
    'installed memory': 'ram',
    ram: 'ram',
    'battery capacity': 'battery',
    'battery life': 'battery',
    battery: 'battery',
    'screen size': 'display',
    screen: 'display',
    monitor: 'display',
    panel: 'display',
    display: 'display',
    'display size': 'display',
    'rear camera': 'camera',
    webcam: 'camera',
    'web camera': 'camera',
    'front camera': 'camera',
    camera: 'camera',
    processor: 'processor',
    cpu: 'processor',
    'cpu model': 'processor',
    chipset: 'processor',
    weight: 'weight',
    'screen resolution': 'resolution',
    resolution: 'resolution',
    os: 'os',
    'operating system': 'os',
    platform: 'os',
    'network type': 'network',
    connectivity: 'network',
    network: 'network',
  }

  if (aliases[text]) return aliases[text]
  if (/(processor|cpu|chipset|core|ryzen|athlon|snapdragon|tensor|apple silicon)/i.test(text)) return 'processor'
  if (/(operating system|windows|macos|android|ubuntu|linux|chrome os)/i.test(text)) return 'os'
  if (/(network|connectivity|wi fi|wifi|bluetooth|cellular|wireless)/i.test(text)) return 'network'
  if (/(ram|memory)/i.test(text)) return 'ram'
  if (/(storage|ssd|hdd|hard disk|hard drive|rom)/i.test(text)) return 'storage'
  if (/(battery|capacity)/i.test(text)) return 'battery'
  if (/(display|screen|panel|monitor)/i.test(text)) return 'display'
  if (/(camera|webcam)/i.test(text)) return 'camera'
  if (/(weight|mass)/i.test(text)) return 'weight'
  if (/(resolution|pixels)/i.test(text)) return 'resolution'
  return text
}

const parseComparableValue = (value, key) => {
  if (value == null || value === '') return null
  const text = String(value)
  const normalizedKey = normalizeFeatureKey(key)
  const allowed = new Set(['ram', 'storage', 'battery', 'display', 'camera', 'processor', 'weight', 'resolution', 'network', 'os'])
  if (!allowed.has(normalizedKey)) return null
  if (['processor', 'network', 'os'].includes(normalizedKey)) return null

  const match = text.match(/(\d+(?:\.\d+)?)(?:\s*(?:gb|mb|tb|ghz|mp|mah|inch|inches|mm|cm|kg|hz|w|v|"))?/i)
  if (!match) return null

  const numeric = Number(match[1])
  return Number.isFinite(numeric) ? numeric : null
}

const extractTextComparableValue = (value, key) => {
  const text = String(value ?? '').trim()
  if (!text) return null

  const normalizedKey = normalizeFeatureKey(key)
  if (normalizedKey === 'processor') {
    const processor = text.match(/(?:intel\s+(?:core\s+)?(?:i[3579]|pentium|celeron)(?:\s+[a-z0-9-]+)?|amd\s+(?:ryzen|athlon)(?:\s+[a-z0-9-]+)?|(?:qualcomm\s+)?snapdragon(?:\s+[0-9]+)?|google\s+tensor(?:\s+[a-z0-9]+)?|apple\s+m[0-9]+|mediatek\s+dimensity(?:\s+[0-9]+)?)/i)
    return processor ? processor[0].replace(/\s+/g, ' ').trim() : null
  }
  if (normalizedKey === 'os') {
    const os = text.match(/(?:windows\s+10|windows\s+11|windows\s+11 pro|windows\s+home|macos|android|linux|ubuntu|chrome\s+os)/i)
    return os ? os[0].replace(/\s+/g, ' ').trim() : null
  }
  if (normalizedKey === 'network') {
    const network = text.match(/(?:wi\s*[- ]?fi|wifi|bluetooth|5g|4g|lte|ethernet)/i)
    return network ? network[0].replace(/\s+/g, ' ').trim() : null
  }

  return null
}

const featurePatterns = [
  { key: 'ram', matchers: [/((?:\d+(?:\.\d+)?)\s*(?:gb|gib))\b[^.;,]{0,24}(?:ram|memory)/i, /(?:ram|memory)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:gb|gib))/i] },
  { key: 'storage', matchers: [/((?:\d+(?:\.\d+)?)\s*(?:gb|tb))\b[^.;,]{0,24}(?:storage|rom|ssd|hdd|internal|disk|drive)/i, /(?:storage|rom|ssd|hdd|internal|disk|drive)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:gb|tb))/i] },
  { key: 'battery', matchers: [/(?:battery|capacity)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:mah|wh))/i, /((?:\d+(?:\.\d+)?)\s*(?:mah))\b[^.;,]{0,16}(?:battery|capacity)/i] },
  { key: 'display', matchers: [/(?:display|screen|panel|monitor)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:in|inch|inches|cm))/i, /((?:\d+(?:\.\d+)?)\s*(?:in|inch|inches|cm))\b[^.;,]{0,16}(?:display|screen|panel|monitor)/i] },
  { key: 'camera', matchers: [/(?:camera|webcam|rear camera|front camera)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:mp|megapixel|megapixels))/i, /((?:\d+(?:\.\d+)?)\s*(?:mp|megapixel|megapixels))\b[^.;,]{0,16}(?:camera|webcam)/i] },
  { key: 'weight', matchers: [/(?:weight|item weight|product weight)\s*[:\-]?\s*((?:\d+(?:\.\d+)?)\s*(?:kg|kilograms?|g|grams))/i, /((?:\d+(?:\.\d+)?)\s*(?:kg|kilograms?|g|grams))\b[^.;,]{0,16}(?:weight)/i] },
  { key: 'resolution', matchers: [/(?:resolution|display|screen)\s*[:\-]?\s*((?:\d+)\s*[x×]\s*(?:\d+))/i, /((?:\d{3,5})\s*[x×]\s*(?:\d{3,5}))/i] },
  { key: 'processor', matchers: [/((?:intel\s+(?:core\s+)?(?:i[3579]|pentium|celeron)(?:\s+[a-z0-9-]+)?|amd\s+(?:ryzen|athlon)(?:\s+[a-z0-9-]+)?|(?:qualcomm\s+)?snapdragon(?:\s+[0-9]+)?|google\s+tensor(?:\s+[a-z0-9]+)?|mediatek\s+dimensity(?:\s+[0-9]+)?|apple\s+m[0-9]+)[^,;]{0,20})/i] },
  { key: 'os', matchers: [/((?:windows\s+10|windows\s+11|macos|android|linux|ubuntu|chrome\s+os)[^,;]{0,30})/i] },
  { key: 'network', matchers: [/((?:wi\s*[- ]?fi|wifi|bluetooth|5g|4g|lte|ethernet)[^,;]{0,20})/i] },
]

const extractComparableProductData = product => {
  const blobs = [
    ...Object.entries(product.specs || {}).map(([key, value]) => `${key} ${value}`),
    product.name,
    product.description,
  ]
  const extracted = {}

  blobs.forEach(blob => {
    if (!blob) return
    const textBlob = String(blob)

    featurePatterns.forEach(({ key, matchers }) => {
      for (const regex of matchers) {
        const match = textBlob.match(regex)
        if (!match) continue

        if (key === 'processor' || key === 'os' || key === 'network') {
          const textValue = extractTextComparableValue(match[1] || textBlob, key)
          if (textValue) extracted[key] = textValue
          break
        }

        const rawText = String(match[1] ?? match[0] ?? '').trim()
        const numeric = Number(String(rawText).replace(/[^0-9.]/g, ''))
        if (!Number.isFinite(numeric) || numeric <= 0) continue

        const unit = rawText.match(/(tb|kg|g)\b/i)?.[1]?.toLowerCase()
        const normalized = unit === 'tb' ? numeric * 1024 : key === 'weight' && numeric > 100 ? numeric / 1000 : numeric
        if (!extracted[key]) extracted[key] = normalized
        break
      }
    })
  })

  return extracted
}

const buildSpecFields = products => {
  const fields = new Map()

  products.forEach((product, productIndex) => {
    const extracted = extractComparableProductData(product)
    const combinedEntries = [
      ...Object.entries(product.specs || {}),
      ...Object.entries(extracted).map(([key, value]) => [key, String(value)]),
    ]

    combinedEntries.forEach(([key, value]) => {
      if (!value) return
      const normalizedKey = normalizeFeatureKey(key)
      if (!normalizedKey) return

      const parsed = parseComparableValue(value, normalizedKey)
      const textValue = extractTextComparableValue(value, normalizedKey)

      if (parsed == null && textValue == null) return

      const field = fields.get(normalizedKey) || {
        id: normalizedKey,
        label: comparableLabels[normalizedKey] || key,
        values: Array(products.length).fill(''),
        numbers: Array(products.length).fill(null),
      }

      field.values[productIndex] = textValue || String(value)
      field.numbers[productIndex] = parsed
      fields.set(normalizedKey, field)
    })
  })

  return [...fields.values()]
    .sort((a, b) => (b.numbers.filter(value => value !== null).length - a.numbers.filter(value => value !== null).length))
    .slice(0, 8)
}

// The product breakdown is an evidence view, not a numeric comparison chart.
// Keep every source-confirmed specification here; buildSpecFields above remains
// intentionally stricter because its values are used to calculate chart bars.
const buildBreakdownFields = products => {
  const fields = new Map()

  const addValue = (key, value, productIndex) => {
    if (value == null || String(value).trim() === '') return
    const normalizedKey = normalizeFeatureKey(key)
    if (!normalizedKey) return

    const field = fields.get(normalizedKey) || {
      id: normalizedKey,
      label: comparableLabels[normalizedKey] || String(key),
      values: Array(products.length).fill(''),
      numbers: Array(products.length).fill(null),
    }

    // Prefer the original retailer/source wording whenever it is available.
    if (!field.values[productIndex]) field.values[productIndex] = formatFeatureValue(key, value)
    fields.set(normalizedKey, field)
  }

  products.forEach((product, productIndex) => {
    Object.entries(product.specs || {}).forEach(([key, value]) => addValue(key, value, productIndex))
    Object.entries(extractComparableProductData(product)).forEach(([key, value]) => addValue(key, value, productIndex))
  })

  return [...fields.values()]
    .sort((a, b) => {
      const coverage = b.values.filter(Boolean).length - a.values.filter(Boolean).length
      return coverage || a.label.localeCompare(b.label)
    })
    .slice(0, 8)
}

/** Normalize different units for a side-by-side feature bar chart. */
const buildRadarData = (fields, products) => {
  const numericFields = [...fields]
  if (numericFields.length < 3 && products.length >= 2) {
    numericFields.push({
      id: 'price',
      label: 'Price',
      values: products.map(product => product.price),
      numbers: products.map(product => priceNumber(product.price) || null),
    })
  }

  return numericFields
  .map(field => ({
    ...field,
    numbers: field.numbers.map(value => (typeof value === 'number' && value > 0 ? value : null)),
  }))
  .filter(field => field.numbers.filter(value => value !== null).length >= 1)
  .slice(0, 6)
  .map(field => {
    const known = field.numbers.filter(value => value !== null)
    if (!known.length) return null
    const low = Math.min(...known)
    const high = Math.max(...known)
    return {
      attribute: field.label,
      fieldId: field.id,
      actualValues: field.values,
      ...Object.fromEntries(field.numbers.map((value, index) => [
        `p${index}`, value === null || value <= 0 ? null : high === low ? 70 : 35 + Math.round(((value - low) / (high - low)) * 65),
      ])),
    }
  })
  .filter(Boolean)
}

function FullSpecificationTable({ products }) {
  const fields = [...new Set(products.flatMap(product => Object.keys(product.specs || {})))].sort((a, b) => a.localeCompare(b))
  if (!fields.length) return <section className="chart-card"><h2>Specification comparison</h2><p className="chart-caption">No structured specifications were returned for these listings.</p></section>
  return <section className="chart-card"><h2>Specification comparison</h2><p className="chart-caption">Every source-provided specification is shown. Empty cells mean that listing did not provide that field.</p><div className="mt-5 overflow-x-auto"><table className="min-w-[720px] w-full text-left text-xs"><thead className="bg-slate-50 text-slate-500"><tr><th className="sticky left-0 bg-slate-50 p-3 font-bold">Specification</th>{products.map((product, index) => <th key={`${productIdentity(product)}-${index}`} className="min-w-44 p-3 font-bold">{shortName(product.name)}</th>)}</tr></thead><tbody>{fields.map(field => <tr key={field} className="border-t border-slate-100"><th className="sticky left-0 bg-white p-3 font-semibold text-slate-600">{field}</th>{products.map((product, index) => <td key={`${field}-${index}`} className="p-3 text-slate-800">{product.specs?.[field] || '—'}</td>)}</tr>)}</tbody></table></div></section>
}

function FeedbackTable({ products }) {
  const available = products.filter(product => product.rating != null)
  if (!available.length) return <section className="chart-card"><h2>Customer Rating</h2><p className="chart-caption">Product ratings appear here when supplied by the source.</p></section>
  return <section className="chart-card"><h2>Customer Rating</h2><p className="chart-caption">Source-provided product ratings.</p><div className="mt-5 space-y-3">{available.map((product, index) => <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 p-3" key={`${productIdentity(product)}-${index}`}><span className="min-w-0 flex-1 truncate font-bold text-slate-800" title={product.name}>{product.name}</span><span className="inline-flex shrink-0 items-center gap-1 text-sm font-bold text-amber-600"><Star size={15} fill="currentColor" />{product.rating}</span></div>)}</div></section>
}

export default function AnalyticsPage({ sessionId, products, selectedProducts, messages, onDeepProducts }) {
  const [history, setHistory] = useState(messages)
  const [recommendation, setRecommendation] = useState(null)
  const [analysisState, setAnalysisState] = useState('idle')
  const [analysisError, setAnalysisError] = useState('')
  useEffect(() => { if (sessionId) getHistory(sessionId).then(result => setHistory(result.data)).catch(() => {}) }, [sessionId])

  // Selection is global to the dashboard: it controls price, coverage, and feature views together.
  const activeProducts = selectedProducts.length ? selectedProducts : products
  const specFields = useMemo(() => buildSpecFields(activeProducts), [activeProducts])
  const breakdownFields = useMemo(() => buildBreakdownFields(activeProducts), [activeProducts])
  const priced = useMemo(() => activeProducts
    .map((product, index) => ({
      ...product,
      id: `${product.name}-${index}`,
      price: priceNumber(product.price),
      shortName: shortName(product.name),
      score: Object.values(product.specs || {}).filter(Boolean).length,
    }))
    .filter(product => product.price), [activeProducts])
  const rated = useMemo(() => {
    const valid = []
    const skipped = []
    activeProducts.forEach((product, index) => {
      const price = priceNumber(product.price)
      const ratingValue = Number(product.rating)
      const hasValidPrice = Number.isFinite(price) && price > 0
      const hasValidRating = Number.isFinite(ratingValue) && ratingValue >= 0 && ratingValue <= 5
      if (hasValidPrice && hasValidRating) {
        valid.push({
          id: `${product.name}-${index}`,
          name: product.name,
          price,
          rating: ratingValue,
          ratingCount: Number(product.rating_count) || 0,
        })
      } else {
        skipped.push(product.name)
      }
    })
    return { data: valid, skippedCount: skipped.length }
  }, [activeProducts])
  const radarData = useMemo(() => buildRadarData(specFields, activeProducts), [specFields, activeProducts])
  const comparableFeatureSummary = useMemo(() => {
    if (!specFields.length) return 'No comparable numeric feature data is available for these listings yet.'
    return `Comparing ${specFields.length} confirmed numeric feature${specFields.length === 1 ? '' : 's'} from the selected listings. Missing source values remain blank.`
  }, [specFields])
  const rankedItems = recommendation?.items || []
  const overallComparison = rankedItems
    .map(item => ({
      name: item.name,
      shortName: shortName(item.name),
      score: Number(item.score_breakdown?.total_score),
    }))
    .filter(item => Number.isFinite(item.score))
    .map(item => ({ ...item, score: Math.round(item.score * 100) }))
  const scoreFor = product => rankedItems.find(item => item.product_key === productIdentity(product))?.score_breakdown?.total_score
  const winner = rankedItems.find(item => item.rank === 1)
  const winnerProduct = winner ? activeProducts.find(product => productIdentity(product) === winner.product_key) : null
  const deepResult = result => { setRecommendation(result); onDeepProducts?.(result.deep_products) }
  const handleAnalysisStateChange = ({ status, error = '' }) => {
    setAnalysisState(status)
    setAnalysisError(error)
    if (status === 'loading') setRecommendation(null)
  }

  if (!products.length) return <main className="mx-auto grid min-h-[70vh] max-w-7xl place-items-center px-5"><div className="max-w-md text-center"><span className="mx-auto grid w-fit rounded-2xl bg-[#f7c96d] p-4 text-[#182230]"><BarChart3 size={34} /></span><h1 className="mt-6 font-serif text-3xl font-black text-[#182230]">Your insights will grow here</h1><p className="mt-3 leading-7 text-[#68717d]">Start a chat to see your comparison analytics here. We’ll turn session listings into helpful price and spec views.</p><Link to="/chat" className="mt-7 inline-block rounded-lg bg-[#182230] px-5 py-3 font-bold text-white">Start a chat</Link></div></main>

  const prices = priced.map(item => item.price)
  const low = prices.length ? Math.min(...prices) : 0
  const high = prices.length ? Math.max(...prices) : 0
  const average = prices.length ? Math.round(prices.reduce((sum, value) => sum + value, 0) / prices.length) : 0
  const scopeMessage = selectedProducts.length
    ? `Showing only the ${activeProducts.length} product${activeProducts.length === 1 ? '' : 's'} you added to comparison.`
    : `Showing all ${activeProducts.length} products in this chat. Add products to comparison to focus every chart.`

  return <main className="analytics-page mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:py-10"><div className="analytics-page-header flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-bold uppercase tracking-[.15em] text-[#e8684c]">Product intelligence</p><h1 className="mt-1 font-serif text-4xl font-black text-[#182230] sm:text-5xl">Product analysis</h1><p className="mt-3 max-w-2xl leading-6 text-[#68717d]">Compare price, ratings, specifications and source-backed customer feedback to understand which product is better and why. {scopeMessage}</p></div><ExportButton /></div>
    <div className="mt-7"><WhyThisPick sessionId={sessionId} products={activeProducts} onResult={deepResult} onAnalysisStateChange={handleAnalysisStateChange} /></div>
    {winner && <section className="mt-7 overflow-hidden rounded-3xl border border-amber-200 bg-amber-50 p-6 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-5"><div><p className="flex items-center gap-2 text-xs font-black uppercase tracking-[.14em] text-amber-800"><Trophy size={16} />Best overall pick</p><h2 className="mt-2 text-2xl font-black text-[#182230]">{winner.name}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-700">{winner.justification || recommendation.summary || 'Highest score from the available price, rating, review sentiment and feature evidence.'}</p></div><div className="rounded-2xl bg-white px-5 py-4 text-center shadow-sm"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Overall score</p><p className="mt-1 text-3xl font-black text-indigo-700">{Math.round((winner.score_breakdown?.total_score || 0) * 100)}</p></div></div><div className="mt-5 flex flex-wrap gap-2">{winner.score_breakdown?.rating_score > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-2 text-xs font-bold text-slate-700"><CheckCircle2 size={14} className="text-emerald-600" />Customer rating considered</span>}{winner.score_breakdown?.review_sentiment_score > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-2 text-xs font-bold text-slate-700"><CheckCircle2 size={14} className="text-emerald-600" />Customer feedback considered</span>}{winner.score_breakdown?.feature_match_score > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-2 text-xs font-bold text-slate-700"><CheckCircle2 size={14} className="text-emerald-600" />Specification match considered</span>}</div>{winnerProduct && <Link to={`/product/${products.findIndex(product => productIdentity(product) === productIdentity(winnerProduct))}`} className="mt-5 inline-block text-sm font-bold text-indigo-700 hover:text-indigo-900">View product details →</Link>}</section>}
    {rankedItems.length > 1 && <section className="chart-card mt-7"><h2>Overall score comparison</h2><p className="chart-caption">Deterministic scores returned by the recommendation engine after deep comparison.</p><div className="mt-5 space-y-3">{rankedItems.map(item => <div className="flex items-center gap-3" key={item.product_key}><span className="w-36 truncate text-xs font-bold text-slate-700" title={item.name}>{item.name}</span><div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-600" style={{ width: `${Math.round((item.score_breakdown?.total_score || 0) * 100)}%` }} /></div><strong className="w-9 text-right text-sm text-slate-800">{Math.round((item.score_breakdown?.total_score || 0) * 100)}</strong></div>)}</div></section>}
    <details className="mt-7 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-bold text-slate-800"><span>Conversation timeline</span><span className="text-xs font-semibold text-indigo-600">Show session history</span></summary><div className="mt-4"><SessionTimeline history={history} /></div></details>
    <section className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="Lowest price" value={prices.length ? `₹${low.toLocaleString('en-IN')}` : 'Unavailable'} detail="Among priced listings" /><StatCard label="Highest price" value={prices.length ? `₹${high.toLocaleString('en-IN')}` : 'Unavailable'} detail="Among priced listings" /><StatCard label="Average price" value={prices.length ? `₹${average.toLocaleString('en-IN')}` : 'Unavailable'} detail="Priced listings only" /><StatCard label="Price range" value={prices.length ? `₹${(high - low).toLocaleString('en-IN')}` : 'Unavailable'} detail={`${activeProducts.length} products in scope`} /></section>
    <section className="mt-7 grid gap-6 xl:grid-cols-2"><PriceChart data={[...priced].sort((a, b) => a.price - b.price)} /><ValueScatterPlot data={overallComparison} analysisState={analysisState} analysisError={analysisError} /></section>
    <section className="mt-7 grid gap-6 xl:grid-cols-[1.3fr_.7fr]"><SpecRadarChart data={radarData} products={activeProducts} summary={comparableFeatureSummary} /><FeedbackTable products={activeProducts} /></section>
    <section className="mt-7"><FullSpecificationTable products={activeProducts} /></section>
    <section className="mt-7"><SpecBreakdownBars fields={breakdownFields} products={activeProducts} /></section>
    <section className="mt-7 chart-card"><h2>Final verdict</h2><p className="chart-caption">Rankings are shown only after the backend returns a deep-comparison score.</p>{rankedItems.length ? <div className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{rankedItems.slice(0, 3).map(item => <div key={item.product_key} className="rounded-2xl border border-slate-200 p-4"><p className="text-xs font-black uppercase tracking-wide text-slate-500">#{item.rank} {item.rank === 1 ? 'Best overall' : 'Comparison rank'}</p><p className="mt-2 font-bold text-slate-800">{item.name}</p>{item.justification && <p className="mt-2 text-xs leading-5 text-slate-600">{item.justification}</p>}</div>)}</div> : <div className="mt-5 grid min-h-28 place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-center text-sm font-medium text-slate-500">{analysisState === 'loading' ? 'Analyzing products...' : analysisState === 'error' ? analysisError || 'Analysis could not be completed. A final verdict is not available.' : analysisState === 'complete' ? 'A final verdict was not available in this recommendation.' : 'Run the AI recommendation to see the final verdict.'}</div>}</section>
  </main>
}
