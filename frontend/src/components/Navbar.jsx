import { BarChart3, MessageSquare, Moon, Plus, Sun } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'

/** Shared responsive site navigation for landing, chat, and analytics routes. */
export default function Navbar({ onNewChat, darkMode, onToggleTheme }) {
  const linkClass = ({ isActive }) => `inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold transition ${isActive ? 'bg-indigo-50 text-indigo-700 shadow-sm ring-1 ring-indigo-100' : 'text-[#68717d] hover:bg-slate-100 hover:text-[#182230]'}`
  return <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/75 shadow-[0_8px_30px_rgba(30,41,59,.05)] backdrop-blur-xl">
    <nav className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
      <Link to="/" className="flex items-center gap-3 text-[#182230]"><span className="relative grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-800 shadow-[0_10px_22px_rgba(79,70,229,.26)] ring-1 ring-white/30 sm:h-14 sm:w-14"><img src="/productgenie-character.avif" alt="ProductGenie character" className="h-full w-full object-contain" onError={event => { event.currentTarget.style.display = 'none' }} /></span><span><strong className="block text-base font-black tracking-tight sm:text-lg">ProductGenie</strong><small className="hidden text-[10px] font-bold uppercase tracking-[.2em] text-indigo-500 sm:block">Research desk</small></span></Link>
      <div className="flex items-center gap-1 sm:gap-3"><NavLink className={linkClass} to="/chat"><MessageSquare size={15} /><span className="hidden sm:inline">Chat</span></NavLink><NavLink className={linkClass} to="/analytics"><BarChart3 size={15} /><span className="hidden sm:inline">Analytics</span></NavLink><button type="button" onClick={onToggleTheme} className="theme-toggle" title={darkMode ? 'Switch to light theme' : 'Switch to dark theme'} aria-label={darkMode ? 'Switch to light theme' : 'Switch to dark theme'}>{darkMode ? <Sun size={17} /> : <Moon size={17} />}</button><Link to="/chat" onClick={onNewChat} className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-2.5 text-sm font-bold text-white shadow-[0_8px_18px_rgba(79,70,229,.25)] hover:bg-indigo-700"><Plus size={15} /><span className="hidden sm:inline">New chat</span></Link></div>
    </nav>
  </header>
}
