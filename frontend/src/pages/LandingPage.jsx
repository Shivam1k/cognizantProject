import { ArrowRight, BotMessageSquare, FileText, SearchCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

const features = [
  [SearchCheck, 'Live Price Search', 'Fresh shopping listings, with source links and prices kept visible.'],
  [BotMessageSquare, 'Photo-Based Search', 'Upload a product photo and start from what is actually in front of you.'],
  [FileText, 'PDF Spec Comparison', 'Turn a spec sheet into a grounded comparison without the spreadsheet work.'],
]

export default function LandingPage() {
  return <main>
    <section className="surface-grid border-b border-[#ddd7cc] bg-[#f4f1eb] px-5 py-16 sm:py-24">
      <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[.9fr_1.1fr]">
        <div><p className="mb-5 inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[.16em] text-[#e8684c]"><Sparkles size={16} /> Shopping, with context</p>
          <h1 className="max-w-xl font-serif text-5xl font-black leading-[.98] tracking-[-.03em] text-[#182230] sm:text-7xl">Buy with a clearer head.</h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-[#68717d]">ProductGenie turns live listings, source details, and your priorities into a decision you can actually trust.</p>
          <div className="mt-8 flex flex-wrap gap-3"><Link to="/chat" className="inline-flex items-center gap-2 rounded-lg bg-[#182230] px-5 py-3 font-bold text-white shadow-lg shadow-[#182230]/15 transition hover:-translate-y-0.5 hover:bg-[#2c3a4b]">Start comparing <ArrowRight size={18} /></Link><Link to="/analytics" className="rounded-lg border border-[#cfc8bc] bg-white px-5 py-3 font-bold text-[#182230] transition hover:border-[#e8684c] hover:text-[#e8684c]">See analytics</Link></div>
        </div>
        <div className="preview-console mx-auto w-full max-w-xl border border-[#d8d1c6] bg-white p-3 sm:p-4">
          <div className="mb-3 flex items-center justify-between border-b border-[#eee9e1] px-1 pb-3 text-[10px] font-bold uppercase tracking-[.16em] text-[#8a8175]"><span>Decision workspace</span><span className="flex items-center gap-1.5 text-[#236054]"><span className="live-pulse h-1.5 w-1.5 rounded-full bg-[#49a883]" />Live research</span></div><div className="grid gap-3 sm:grid-cols-[1.05fr_.95fr]"><div className="bg-[#182230] p-5 text-white sm:p-6"><div className="mb-9 flex items-center gap-2 text-sm font-bold"><span className="grid h-7 w-7 place-items-center overflow-hidden rounded-lg bg-[#f7c96d]"><img src="/productgenie-character.avif" alt="" className="h-full w-full object-contain" /></span>ProductGenie<span className="ml-auto text-[10px] uppercase tracking-widest text-[#f7c96d]">Advisor</span></div><p className="max-w-[220px] rounded-lg bg-[#2c3a4b] p-4 text-sm font-bold leading-6">I need a laptop for coding under ₹65,000.</p><p className="mt-3 max-w-[245px] rounded-lg bg-[#e8684c] p-4 text-sm font-bold leading-6">I’ll compare processor, RAM, and price from live listings.</p><div className="mt-10 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-[#9ba8b7]"><span className="h-1.5 w-1.5 rounded-full bg-[#e8684c]" />Source-backed results</div></div><div className="space-y-3 bg-[#f8f6f1] p-4"><div className="flex items-center justify-between"><p className="text-xs font-black uppercase tracking-wider text-[#8a8175]">Live matches</p><span className="rounded-full bg-[#c5e4da] px-2 py-1 text-[10px] font-bold text-[#236054]">2 found</span></div>{['Top pick · ₹59,990', 'Value option · ₹54,499'].map((label, index) => <div className="rounded-lg border border-[#ddd7cc] bg-white p-3 shadow-sm" key={label}><div className={`mb-3 flex h-16 items-end gap-1 px-4 ${index ? 'bg-[#edf6f2]' : 'bg-[#fff8e6]'}`}><span className={`w-8 rounded-t-lg ${index ? 'h-10 bg-[#9fd2c3]' : 'h-14 bg-[#f7c96d]'}`} /><span className={`w-8 rounded-t-lg ${index ? 'h-14 bg-[#c5e4da]' : 'h-10 bg-[#e7b85c]'}`} /><span className="h-7 w-8 rounded-t-lg bg-[#e5e0d7]" /></div><p className="text-xs font-black text-[#182230]">{label}</p><p className="mt-1 text-[10px] text-[#8a8175]">RAM · processor · verified source</p></div>)}</div></div>
        </div>
      </div>
    </section>
    <section id="about" className="mx-auto max-w-7xl px-5 py-20"><div className="mx-auto mb-12 max-w-2xl text-center"><h2 className="font-serif text-3xl font-black text-[#182230]">Decisions backed by the details</h2><p className="mt-3 text-[#68717d]">Every recommendation is tied to a live listing or document you supplied.</p></div><div className="grid gap-5 md:grid-cols-3">{features.map(([Icon, title, text], index) => <article className="border border-[#ddd7cc] bg-white p-7 shadow-[0_12px_28px_rgba(24,34,48,.05)]" key={title}><span className={`inline-grid p-3 ${index === 1 ? 'bg-[#c5e4da] text-[#236054]' : 'bg-[#f7c96d] text-[#182230]'}`}><Icon size={24} /></span><h3 className="mt-5 text-lg font-bold text-[#182230]">{title}</h3><p className="mt-2 leading-7 text-[#68717d]">{text}</p></article>)}</div></section>
  </main>
}
