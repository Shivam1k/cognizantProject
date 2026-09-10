import { FileText } from 'lucide-react'

/** Select a PDF specification sheet for parsing. */
export default function PDFUpload({ onSelect, disabled }) {
  return <label title="Upload PDF spec sheet" className={`cursor-pointer rounded-lg p-2 text-slate-500 hover:bg-slate-100 ${disabled ? 'pointer-events-none opacity-40' : ''}`}>
    <FileText size={19} /><input className="hidden" type="file" accept="application/pdf" onChange={e => e.target.files?.[0] && onSelect(e.target.files[0])} />
  </label>
}
