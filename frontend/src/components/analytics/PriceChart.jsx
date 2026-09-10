import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export default function PriceChart({ data }) {
  return <section className="chart-card"><h2>Price comparison</h2><p className="chart-caption">Listings are sorted from lowest to highest price.</p><div className="h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 12, right: 12, left: 4, bottom: 42 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="shortName" angle={-25} textAnchor="end" interval={0} tick={{ fontSize: 11 }} /><YAxis tickFormatter={value => `₹${Math.round(value / 1000)}k`} width={52} /><Tooltip formatter={value => [`₹${Number(value).toLocaleString('en-IN')}`, 'Price']} /><Bar dataKey="price" fill="#4f46e5" radius={[7, 7, 0, 0]} /></BarChart></ResponsiveContainer></div></section>
}
