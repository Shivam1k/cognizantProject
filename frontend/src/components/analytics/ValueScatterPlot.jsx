import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/** Presents recommendation-engine scores only; it does not calculate scores. */
export default function ValueScatterPlot({ data, analysisState, analysisError }) {
  if (!data.length) {
    const message = analysisState === 'loading'
      ? 'Analyzing products...'
      : analysisState === 'error'
        ? analysisError || 'Analysis could not be completed. Overall scores are not available.'
        : analysisState === 'complete'
          ? 'Overall scores were not available in this recommendation.'
          : 'Run the AI recommendation to generate overall scores for the current shortlist.'
    return <section className="chart-card"><h2>Overall Comparison</h2><p className="chart-caption">Existing overall scores returned by the recommendation engine for the current products.</p><div className="mt-5 grid h-72 place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-center text-sm font-medium text-slate-500">{message}</div></section>
  }
  return <section className="chart-card"><h2>Overall Comparison</h2><p className="chart-caption">Existing overall scores returned by the recommendation engine for the current products.</p><div className="h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 12, right: 12, left: 4, bottom: 52 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="shortName" angle={-24} textAnchor="end" interval={0} tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} tickFormatter={value => `${value}`} width={40} /><Tooltip formatter={value => [value, 'Overall score']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name || ''} /><Bar dataKey="score" fill="#4f46e5" radius={[7, 7, 0, 0]} maxBarSize={48} /></BarChart></ResponsiveContainer></div></section>
}
