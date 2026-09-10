export default function StatCard({ label, value, detail }) {
  return <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_5px_18px_rgba(30,41,59,.05)]"><p className="text-xs font-bold uppercase tracking-[.12em] text-slate-500">{label}</p><p className="mt-2 text-2xl font-black tracking-tight text-slate-900">{value}</p><p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p></article>
}
