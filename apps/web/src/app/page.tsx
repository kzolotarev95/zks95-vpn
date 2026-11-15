import Link from "next/link";
import { ArrowDown, ArrowUpRight, Fingerprint, Globe2, Layers3, LockKeyhole, ShieldCheck } from "lucide-react";
import { Header } from "@/components/header";
import { Plans } from "@/components/plans";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/ui/button";

export default function Home() {
  return <>
    <Header />
    <main>
      <section className="hero wrap">
        <Reveal className="hero-copy">
          <div className="eyebrow"><span className="gold-dot" /> ВАШЕ ЛИЧНОЕ ПРОСТРАНСТВО</div>
          <h1>Свобода быть<br /><span>на связи.</span></h1>
          <p className="hero-text">Интернет — часть вашей жизни.<br />Мы создаём VPN, который делает эту часть<br className="desktop-br" /> спокойнее, проще и безопаснее.</p>
          <div className="hero-actions"><Button asChild><Link href="/#plans">Выбрать свой тариф <ArrowUpRight size={18} /></Link></Button><Link className="text-link" href="#approach">Познакомиться <ArrowDown size={16} /></Link></div>
          <div className="launch-note"><span className="launch-line" /> Ранний доступ · сервис готовится к запуску</div>
        </Reveal>
        <Reveal className="hero-art">
          <div className="orbital" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orbit-cross horizontal" /><div className="orbit-cross vertical" /><div className="orbital-core"><ShieldCheck size={70} strokeWidth={1} /></div><span className="orbit-point point-one" /><span className="orbit-point point-two" /><span className="orbit-point point-three" /></div>
          <div className="art-label art-label-top"><LockKeyhole size={14} /> PRIVATE BY DESIGN</div>
          <div className="art-label art-label-bottom"><span className="gold-dot" /> ZKS95 / SECURE CONNECTION</div>
          <div className="art-coordinate">55°45′ N &nbsp; / &nbsp; 37°37′ E</div>
        </Reveal>
      </section>
      <div className="principles-strip"><div className="wrap"><span><ShieldCheck size={18} /> Приватность по умолчанию</span><span><Layers3 size={18} /> Один аккаунт для устройств</span><span><Globe2 size={18} /> Подключение без сложностей</span></div></div>
      <section className="section wrap" id="approach">
        <Reveal><div className="eyebrow">01 / НАШ ПОДХОД</div><div className="section-heading"><h2>Меньше лишнего.<br /><span>Больше вашего.</span></h2><p>Продуманная защита начинается с простых вещей: понятного интерфейса, прозрачных условий и контроля в ваших руках.</p></div></Reveal>
        <div className="features-grid">{[
          { Icon: Fingerprint, title: "Ваш доступ — под контролем", text: "Личный кабинет хранит ваши заказы и подписки в одном месте. Без поиска нужного сообщения или ссылки." },
          { Icon: Layers3, title: "Для вашего ритма жизни", text: "Выбирайте срок и количество устройств. Условия тарифа фиксируются при создании заказа." },
          { Icon: ShieldCheck, title: "Внимание к деталям", text: "Защищённые сессии, проверка запросов и изоляция данных аккаунтов заложены в основу платформы." },
        ].map(({ Icon, title, text }, i) => <Reveal key={title} className="feature-card"><div className="feature-icon"><Icon size={25} strokeWidth={1.4} /></div><span className="feature-number">0{i + 1}</span><h3>{title}</h3><p>{text}</p></Reveal>)}</div>
      </section>
      <section className="section plans-section" id="plans"><div className="wrap"><Reveal><div className="eyebrow">02 / ВЫБЕРИТЕ СВОЙ ПЛАН</div><div className="section-heading"><h2>Свобода.<br /><span>На ваших условиях.</span></h2><p>Начните с комфортного срока.<br />Оплата и выдача VPN-доступа откроются после завершения подготовки сервиса.</p></div></Reveal><Plans /><p className="plans-note">Можно создать аккаунт и сохранить заказ. Сейчас оплата не принимается.</p></div></section>
      <section className="section wrap faq-section" id="faq"><div><div className="eyebrow">03 / ВСЁ ПОНЯТНО</div><h2>Есть вопросы?<br /><span>Есть ответы.</span></h2></div><div className="faq-list">{[
        ["Сервис уже работает?", "Платформа находится в разработке. Регистрация, личный кабинет и заказы уже доступны. Платежи и реальные VPN-подключения будут открыты после проверки интеграций."],
        ["Когда я получу VPN-конфигурацию?", "После запуска сервиса, успешной оплаты и активации подписки. Создание заказа само по себе не выдаёт доступ и не списывает деньги."],
        ["Какие протоколы планируются?", "В первой версии — VLESS Reality, WireGuard и AmneziaWG. Список доступных локаций появится после подключения и проверки серверов."],
        ["Где находятся мои заказы?", "Войдите в личный кабинет с email и паролем. Заказы доступны только вашему аккаунту."],
      ].map(([question, answer]) => <details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}</div></section>
    </main>
    <footer className="wrap footer"><Link href="/" className="brand">ZKS95<span className="brand-vpn">VPN</span></Link><span>Ваше пространство. Ваши правила.</span><span>© {new Date().getFullYear()} ZKS95 VPN</span></footer>
  </>;
}
