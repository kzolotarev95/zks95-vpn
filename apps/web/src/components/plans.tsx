"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Check, RefreshCw } from "lucide-react";
import { api, type Plan } from "@/lib/api";
import { money } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function Plans() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState("");
  async function load() {
    setError("");
    try { setPlans(await api<Plan[]>("/plans")); }
    catch { setError("Не удалось загрузить тарифы. Попробуйте ещё раз."); }
  }
  useEffect(() => {
    const controller = new AbortController();
    api<Plan[]>("/plans", { signal: controller.signal }).then(setPlans).catch((e) => {
      if (e.name !== "AbortError") setError("Не удалось загрузить тарифы. Попробуйте ещё раз.");
    });
    return () => controller.abort();
  }, []);
  if (error) return <div className="empty-state"><p role="alert">{error}</p><Button variant="outline" onClick={load}><RefreshCw size={16} /> Повторить</Button></div>;
  if (!plans) return <div className="loading-plans" aria-busy="true">Загружаем актуальные тарифы…</div>;
  if (!plans.length) return <div className="empty-state">Тарифы появятся перед запуском сервиса.</div>;
  return <div className="plans-grid">{plans.map((plan, index) =>
    <article className={`plan-card ${index === 1 ? "plan-featured" : ""}`} key={plan.id}>
      <div className="plan-top"><span>0{index + 1} / ПОДПИСКА</span>{index === 1 && <span className="tag">БАЛАНС</span>}</div>
      <h3>{plan.name}</h3><p className="plan-description">{plan.description}</p>
      <div className="price">{money(plan.price_minor, plan.currency)}<span> / {plan.duration_days} дней</span></div>{plan.stars_price && <p className="plan-payment">Telegram Stars: {plan.stars_price} XTR · ЮKassa на сайте</p>}
      <ul className="plan-features"><li><Check size={16} /> До {plan.device_limit} устройств</li><li><Check size={16} /> Единый личный кабинет</li><li><Check size={16} /> Срок и цена фиксируются в заказе</li></ul>
      <Button asChild variant={index === 1 ? "default" : "outline"}><Link href={`/dashboard?plan=${encodeURIComponent(plan.id)}`}>Выбрать тариф <ArrowUpRight size={17} /></Link></Button>
    </article>
  )}</div>;
}
