/** Compare only listed facts, with price-aware colour cues where values are numeric. */
export default function ComparisonTable({ products }) {
  const fields = ['Price', ...new Set(products.flatMap(product => Object.keys(product.specs || {})))].slice(0, 8)
  const numeric = value => Number(String(value).replace(/[^0-9.]/g, '')) || null
  const cellClass = (field, value) => {
    // A larger number is not inherently better: weight, charge time, and size
    // are preference-dependent. Only price has a universal direction here.
    if (field !== 'Price') return 'bg-slate-50 text-slate-700'
    const values = products.map(product => numeric(field === 'Price' ? product.price : product.specs?.[field])).filter(Boolean)
    const current = numeric(value)
    if (!current || values.length < 2) return 'bg-slate-50 text-slate-700'
    const best = Math.min(...values)
    const worst = Math.max(...values)
    if (best !== worst && current === best) return 'bg-emerald-50 text-emerald-800'
    if (best !== worst && current === worst) return 'bg-rose-50 text-rose-800'
    return 'bg-slate-50 text-slate-700'
  }
  if (products.length < 2) return <p className="rounded-xl border border-[#e5e0d7] bg-[#f8f6f1] p-6 text-center text-sm text-[#68717d]">Select at least two products to compare their details.</p>
  return <div className="overflow-x-auto rounded-xl border border-[#e5e0d7]"><table className="min-w-[620px] w-full text-left text-xs"><thead className="sticky top-0 z-10 bg-[#182230] text-white"><tr><th className="p-4 text-[#f7c96d]">Attribute</th>{products.map(product => <th className="p-4" key={`${product.name}-${product.price}`}>{product.name}</th>)}</tr></thead><tbody>{fields.map(field => <tr className="border-t border-[#eee9e1]" key={field}><td className="bg-[#f4f1eb] p-4 font-bold text-[#68717d]">{field}</td>{products.map(product => { const value = field === 'Price' ? product.price : product.specs?.[field] || '—'; return <td className={`p-4 ${cellClass(field, value)}`} key={`${product.name}-${field}`}>{value}</td> })}</tr>)}</tbody></table></div>
}
