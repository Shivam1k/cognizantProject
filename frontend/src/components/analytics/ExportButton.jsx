import { Download } from 'lucide-react'

export default function ExportButton() { return <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2.5 text-sm font-bold text-white shadow-[0_6px_16px_rgba(15,23,42,.16)] transition hover:bg-slate-700"><Download size={16} />Export comparison</button> }
