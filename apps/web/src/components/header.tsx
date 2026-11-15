import Link from "next/link";
import { ArrowUpRight, Shield } from "lucide-react";

export function Header() {
  return <header className="header wrap">
    <Link href="/" className="brand" aria-label="ZKS95 VPN — главная">
      <span className="brand-icon"><Shield size={23} strokeWidth={1.7} /></span>
      <span>ZKS95<span className="brand-vpn">VPN</span></span>
    </Link>
    <nav aria-label="Главная навигация"><Link href="/#approach">Преимущества</Link><Link href="/#plans">Тарифы</Link><Link href="/#faq">Вопросы</Link></nav>
    <Link href="/dashboard" className="header-account">Личный кабинет <ArrowUpRight size={16} /></Link>
  </header>;
}
