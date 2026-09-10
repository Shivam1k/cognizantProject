import { Bot, Search } from 'lucide-react'

export default function SessionTimeline({ history }) {
  return <section className="chart-card"><h2>Conversation timeline</h2><p className="chart-caption">Key moments from this shopping session.</p><div className="mt-5 space-y-4 border-l-2 border-indigo-100 pl-5">{history.slice(0, 8).map((item, index) => <div className="relative" key={`${item.role}-${index}`}><span className="absolute -left-8 grid h-5 w-5 place-items-center rounded-full bg-indigo-100 text-indigo-600">{item.role === 'user' ? <Search size={11} /> : <Bot size={11} />}</span><p className="text-xs font-bold uppercase tracking-wide text-slate-500">{item.role === 'user' ? 'Search or preference' : 'Recommendation'}</p><p className="mt-1 line-clamp-2 text-sm text-slate-700">{item.content}</p></div>)}</div></section>
}
