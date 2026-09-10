/** Context-sensitive prompts that continue a product conversation in one click. */
export default function QuickReplyChips({ onChoose }) {
  return <div className="mt-3 flex flex-wrap gap-2">{['Compare the top two', 'Which is the best value?', 'What if my priority changes?'].map(item => <button type="button" onClick={() => onChoose(item)} key={item} className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition hover:-translate-y-0.5 hover:bg-indigo-100">{item}</button>)}</div>
}
