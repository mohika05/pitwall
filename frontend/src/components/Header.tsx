import { ConnectionStatus } from './ConnectionStatus'
export function Header({ archivePending = false }: { archivePending?: boolean }) {
  return <header className="header"><div className="brand-lockup"><span className="brand-mark" aria-hidden="true">╱╱</span><div><div className="brand">PITWALL<span> / </span></div><div className="subtitle">FORMULA 1 · RACE ENGINEERING</div></div></div><ConnectionStatus archivePending={archivePending} /></header>
}
