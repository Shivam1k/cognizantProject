const cleanProductLabel = name => name.length > 28 ? `${name.slice(0, 28)}…` : name

const readableValue = (field, value, sourceValue) => {
  const sourceText = String(sourceValue ?? '').trim()
  // Processor, OS, and network are source-confirmed text fields. They do not
  // have a numeric chart value, so display their original value directly.
  if (['processor', 'os', 'network'].includes(field.id)) return sourceText || 'Not listed'

  if (value == null || value === '' || Number.isNaN(Number(value))) return sourceText || 'Not listed'
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return sourceText || 'Not listed'

  if (field.id === 'ram') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)} GB`
  if (field.id === 'storage') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)} GB`
  if (field.id === 'battery') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(0)} mAh`
  if (field.id === 'display') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)} in`
  if (field.id === 'camera') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)} MP`
  if (field.id === 'weight') return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)} kg`
  if (field.id === 'resolution') return String(value)
  return String(value)
}

export default function SpecBreakdownBars({ fields, products }) {
  if (!fields.length) return <section className="chart-card"><h2>Product-specific feature breakdown</h2><p className="chart-caption">No source-confirmed feature details are available for these listings yet.</p></section>
  return <section className="chart-card"><h2>Product-specific feature breakdown</h2><p className="chart-caption">Each field below shows only selected listings with a confirmed value in its source details.</p><div className="mt-5 space-y-4">{fields.map(field => {
    const availableProducts = products.map((product, index) => ({ product, index })).filter(({ index }) => field.numbers[index] != null || String(field.values[index] ?? '').trim())
    return <div key={field.id} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3"><div className="mb-2 flex items-center justify-between gap-3"><p className="text-sm font-bold text-slate-800">{field.label}</p><span className="rounded-full bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">{availableProducts.length}/{products.length}</span></div><div className="grid gap-2">{availableProducts.map(({ product, index }) => <div className="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2 text-xs shadow-sm ring-1 ring-slate-200" key={`${product.name}-${index}`}><span className="max-w-[46%] truncate font-medium text-slate-600" title={product.name}>{cleanProductLabel(product.name)}</span><strong className="max-w-[52%] truncate text-right font-semibold text-slate-800" title={readableValue(field, field.numbers[index], field.values[index])}>{readableValue(field, field.numbers[index], field.values[index])}</strong></div>)}</div></div>
  })}</div></section>
}
