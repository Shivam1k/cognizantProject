/** Compact product evidence shown alongside an assistant review. */
export default function InlineProductCard({ product }) {
  return <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-sm"><div className="h-10 w-10 overflow-hidden rounded-lg bg-slate-100">{product.imageUrl && <img className="h-full w-full object-cover" src={product.imageUrl} alt="" />}</div><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold text-slate-800">{product.name}</p><p className="text-xs font-bold text-indigo-700">{product.price}</p></div><span className="max-w-20 truncate rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{product.source}</span></div>
}
