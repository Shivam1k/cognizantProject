import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const palette = ['#4f46e5', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#0ea5e9', '#84cc16', '#ec4899']

const readableValue = (fieldId, value) => {
  if (value == null || value === '') return 'Not listed'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  const units = { ram: 'GB', storage: 'GB', battery: 'mAh', display: 'in', camera: 'MP', weight: 'kg', price: 'INR' }
  const formatted = fieldId === 'price' ? numeric.toLocaleString('en-IN') : Number.isInteger(numeric) ? numeric : numeric.toFixed(1)
  return `${formatted}${units[fieldId] ? ` ${units[fieldId]}` : ''}`
}

const FeatureTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"><p className="font-bold text-slate-900">{label}</p><div className="mt-1 grid gap-1">{payload.map(item => <p key={item.dataKey} className="text-slate-600"><span className="font-semibold" style={{ color: item.fill }}>{item.name}</span>: {readableValue(point.fieldId, point.actualValues[item.dataKey.slice(1)])}</p>)}</div><p className="mt-1 text-[10px] text-slate-400">Bars are scaled within each feature; values above are exact.</p></div>
}

/** Grouped bars make per-feature product differences easier to scan than a radar chart. */
export default function SpecRadarChart({ data, products, summary }) {
  if (!data.length) return <section className="chart-card"><h2>Comparable numeric features</h2><p className="chart-caption">There are no source-confirmed numeric features to plot yet.</p></section>
  return <section className="chart-card"><h2>Comparable numeric features</h2><p className="chart-caption">{summary || 'Each group is scaled within that feature so different units remain easy to compare. Hover a bar for the exact source value.'}</p><div className="h-80"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 20, right: 12, left: 10, bottom: 8 }} barGap={3}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="attribute" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} tickFormatter={value => `${value}%`} width={50} tickMargin={8} /><Tooltip content={<FeatureTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />{products.map((product, index) => <Bar key={`${product.name}-${index}`} name={product.name} dataKey={`p${index}`} fill={palette[index % palette.length]} radius={[4, 4, 0, 0]} maxBarSize={28} />)}</BarChart></ResponsiveContainer></div></section>
}
