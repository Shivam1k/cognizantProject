import { forwardRef } from 'react'
import { ArrowRightLeft, BadgeCheck, Check, ImageOff, Sparkles, Star } from 'lucide-react'
import { Link } from 'react-router-dom'

/** Evidence card for a listing in the current product category. */
const ProductCard = forwardRef(function ProductCard({ product, selected, onToggleComparison, highlighted = false, detailsPath }, ref) {
  const specs = Object.entries(product.specs || {}).filter(([key, value]) => {
    if (!/battery|capacity/i.test(key)) return true
    const match = String(value).match(/(\d+(?:\.\d+)?)\s*mAh/i)
    return !match || Number(match[1]) >= 1000
  }).slice(0, 5)
  const attributes = Object.entries(product.attributes || {})
    .map(([key, value]) => [key, value?.value ?? value])
    .filter(([, value]) => value != null && String(value).trim())
    .filter(([key]) => !Object.keys(product.specs || {}).some(specKey => specKey.toLowerCase() === key.toLowerCase()))
    .slice(0, 3)
  const source = product.source || 'Source unavailable'
  return <article ref={ref} className={`group relative overflow-hidden rounded-3xl border bg-white p-4 shadow-[0_8px_24px_rgba(30,41,59,.06)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_18px_38px_rgba(30,41,59,.12)] ${highlighted ? 'border-indigo-400 ring-2 ring-indigo-200 ring-offset-2' : 'border-slate-200'}`}>
    {product.recommended && <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-bold text-amber-700"><Sparkles size={11} />Top pick</span>}
    <div className="flex gap-3">{detailsPath ? <Link to={detailsPath} aria-label={`Open details for ${product.name}`} className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-2xl bg-slate-100 ring-1 ring-slate-200/60">{product.imageUrl ? <img src={product.imageUrl} alt="" className="h-full w-full object-cover transition duration-300 group-hover:scale-105" onError={event => { event.currentTarget.style.display = 'none' }} /> : <ImageOff className="text-slate-400" />}</Link> : <div className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-2xl bg-slate-100">{product.imageUrl ? <img src={product.imageUrl} alt="" className="h-full w-full object-cover" onError={event => { event.currentTarget.style.display = 'none' }} /> : <ImageOff className="text-slate-400" />}</div>}<div className="min-w-0 flex-1">{detailsPath ? <Link to={detailsPath} className="line-clamp-2 text-sm font-bold leading-5 text-slate-800 hover:text-indigo-700">{product.name}</Link> : <h3 className="line-clamp-2 text-sm font-bold text-slate-800">{product.name}</h3>}<p className="mt-2 text-xl font-extrabold tracking-tight text-indigo-700">{product.price}</p>{product.link ? <a href={product.link} target="_blank" rel="noopener noreferrer" title={`Open source: ${source}`} className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600 hover:text-indigo-700">{product.verified && <BadgeCheck size={12} className="shrink-0 text-emerald-600" />}{source}</a> : <span className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">{product.verified && <BadgeCheck size={12} className="shrink-0 text-emerald-600" />}{source}</span>}{product.rating != null && <p className="mt-2 flex items-center gap-1 text-xs font-semibold text-amber-600"><Star size={14} fill="currentColor" />{product.rating}{product.rating_count != null && <span className="text-slate-500">({Number(product.rating_count).toLocaleString('en-IN')})</span>}</p>}{product.delivery && <span className="mt-2 inline-block rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700">{product.delivery}</span>}</div></div>
    {product.description && <p className="mt-4 line-clamp-3 text-xs leading-5 text-slate-600">{product.description}</p>}
    <div className="mt-4 space-y-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500">{specs.map(([key, value]) => <p className="flex justify-between gap-3" key={key}><span>{key}</span><strong className="truncate text-slate-700">{value}</strong></p>)}{attributes.map(([key, value]) => <p className="flex justify-between gap-3" key={key}><span>{key}</span><strong className="truncate text-slate-700">{String(value)}</strong></p>)}</div>
    <div className="mt-4 flex justify-center"><button type="button" onClick={() => onToggleComparison(product)} className={`rounded-xl px-3 py-2 text-xs font-bold transition ${selected ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200 hover:bg-indigo-700' : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100'}`}>{selected ? <><Check className="mr-1 inline" size={14} />Selected</> : <><ArrowRightLeft className="mr-1 inline" size={14} />Compare</>}</button></div>
  </article>
})

export default ProductCard
