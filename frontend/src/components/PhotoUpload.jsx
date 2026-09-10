import { Camera } from 'lucide-react'

/** Select a photo, then pass it to the common upload handler. */
export default function PhotoUpload({ onSelect, disabled }) {
  return <label title="Identify product from photo" className={`cursor-pointer rounded-lg p-2 text-slate-500 hover:bg-slate-100 ${disabled ? 'pointer-events-none opacity-40' : ''}`}>
    <Camera size={19} /><input className="hidden" type="file" accept="image/*" onChange={e => e.target.files?.[0] && onSelect(e.target.files[0])} />
  </label>
}
