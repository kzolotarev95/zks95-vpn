"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Check, Clock3, LogOut, ShieldCheck } from "lucide-react";
import { api, ApiError, type Order, type Payment, type Plan, type Subscription, type User } from "@/lib/api";
import { money } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { TelegramLink } from "@/components/telegram-link";

const statuses: Record<Order["status"], string> = { pending: "Ожидает оплаты", paid: "Оплачен", cancelled: "Отменён", refunded: "Возврат" };

function fetchAccount() {
  return Promise.all([
    api<User>("/me"), api<Plan[]>("/plans"), api<Order[]>("/orders"), api<Subscription[]>("/subscriptions"),
  ]);
}

export function Account() {
  const params = useSearchParams();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [selected, setSelected] = useState(params.get("plan") || "");
  const [pendingKey, setPendingKey] = useState<{ plan: string; key: string } | null>(null);

  const loadAccount = useCallback(async () => {
    const [current, catalog, history, active] = await fetchAccount();
    setUser(current); setPlans(catalog); setOrders(history); setSubscriptions(active);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchAccount().then(([current, catalog, history, active]) => {
      if (cancelled) return;
      setUser(current); setPlans(catalog); setOrders(history); setSubscriptions(active);
    }).catch((e) => {
      if (cancelled) return;
      if (!(e instanceof ApiError && e.status === 401)) setError(e.message);
    }).finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const orderId = params.get("payment");
    if (!user || !orderId) return;
    let stopped = false;
    const poll = async () => {
      try {
        const payment = await api<Payment>(`/orders/${orderId}/payment`);
        if (stopped) return;
        if (payment?.status === "succeeded") {
          setNotice("Оплата подтверждена. VPN-доступ активируется автоматически.");
          await loadAccount();
          return;
        }
      } catch { /* The return page can briefly load before the session is restored. */ }
      if (!stopped) window.setTimeout(poll, 3000);
    };
    void poll();
    return () => { stopped = true; };
  }, [params, user, loadAccount]);

  async function authenticate(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api<User>(register ? "/auth/register" : "/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setPassword(""); await loadAccount();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось войти"); }
    finally { setBusy(false); }
  }

  async function logout() {
    setBusy(true); setError("");
    try { await api<void>("/auth/logout", { method: "POST" }); setUser(null); setOrders([]); setSubscriptions([]); setNotice(""); setPendingKey(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Ошибка выхода"); }
    finally { setBusy(false); }
  }

  async function createOrder(event: React.FormEvent) {
    event.preventDefault(); if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    const key = pendingKey?.plan === selected ? pendingKey.key : crypto.randomUUID();
    setPendingKey({ plan: selected, key });
    try {
      const order = await api<Order>("/orders", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ plan_id: selected }) });
      setOrders((current) => [order, ...current.filter((item) => item.id !== order.id)]);
      setPendingKey(null);
      try {
        const payment = await api<Payment>(`/orders/${order.id}/payments/yookassa`, { method: "POST" });
        if (payment.confirmation_url) window.location.assign(payment.confirmation_url);
        else setNotice("Платёж создан. Откройте ссылку оплаты из истории заказа.");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) setNotice("Заказ сохранён. ЮKassa ещё не настроена или платёж уже создан.");
        else throw e;
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось создать заказ"); }
    finally { setBusy(false); }
  }

  async function payOrder(order: Order) {
    setBusy(true); setError("");
    try {
      const payment = await api<Payment>(`/orders/${order.id}/payments/yookassa`, { method: "POST" });
      if (payment.confirmation_url) window.location.assign(payment.confirmation_url);
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось открыть оплату"); }
    finally { setBusy(false); }
  }

  if (!ready) return <div className="empty-state" aria-busy="true">Открываем ваше пространство…</div>;
  if (!user) return <div className="auth-layout"><section className="auth-intro"><div className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</div><h1>Всё ваше.<br /><span>В одном месте.</span></h1><p>Подписки, заказы и управление доступом.<br />Войдите, чтобы продолжить.</p><ShieldCheck size={96} strokeWidth={0.7} /></section><section className="auth-card"><div className="auth-tabs"><button className={!register ? "active" : ""} onClick={() => { setRegister(false); setError(""); }}>Войти</button><button className={register ? "active" : ""} onClick={() => { setRegister(true); setError(""); }}>Создать аккаунт</button></div><h2>{register ? "Начнём знакомство" : "С возвращением"}</h2><p>{register ? "Создайте ваше личное пространство." : "Рады видеть вас снова."}</p><form onSubmit={authenticate}><label>Email<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} placeholder="you@example.com" /></label><label>Пароль<input type="password" required minLength={5} maxLength={128} autoComplete={register ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Не менее 5 символов" /></label>{error && <p className="form-error" role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy ? "Подождите…" : register ? "Создать аккаунт" : "Войти в кабинет"}<ArrowRight size={17} /></Button></form><p className="auth-note">После входа доступны ЮKassa и история платежей.</p></section></div>;

  return <>
    <TelegramLink />
    <div className="account-heading"><div><div className="eyebrow">ВАШЕ ПРОСТРАНСТВО</div><h1>Личный кабинет<span>.</span></h1><p>{user.email}</p></div><Button variant="outline" onClick={logout} disabled={busy}><LogOut size={16} /> Выйти</Button></div>
    <div className="account-banner"><ShieldCheck size={25} /><div><strong>Оплата и подключение в одном кабинете.</strong><p>Оплатите заказ через ЮKassa. После подтверждения доступ из 3x-ui или Remnawave появится автоматически.</p></div><span className="tag">ЮKASSA</span></div>
    {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="form-success" role="status"><Check size={17} />{notice}</p>}
    <div className="account-grid"><section className="panel"><div className="panel-title"><h2>Мои подписки</h2><ShieldCheck size={19} /></div>{subscriptions.length ? subscriptions.map((sub) => <div key={sub.id} className="subscription-row"><strong>{sub.plan_name}</strong><p>{sub.status === "active" ? "Активна" : sub.status === "expired" ? "Истекла" : "Отозвана"} · до {new Date(sub.expires_at).toLocaleDateString("ru-RU")} · {sub.device_limit} устройств{sub.provider_name ? ` · ${sub.provider_name}` : ""}</p>{sub.connection_url && <a className="text-link" href={sub.connection_url} target="_blank" rel="noreferrer">Открыть ссылку подписки <ArrowRight size={14} /></a>}</div>) : <div className="empty-state"><ShieldCheck size={36} strokeWidth={1} /><h3>Здесь начнётся ваше подключение</h3><p>Активных подписок пока нет.<br />После подтверждённой оплаты они появятся здесь.</p></div>}</section>
    <section className="panel"><div className="panel-title"><h2>Новый заказ</h2><ArrowRight size={19} /></div><form onSubmit={createOrder} className="order-form"><label>Выберите тариф<select value={selected} onChange={(e) => { setSelected(e.target.value); setPendingKey(null); }} required><option value="" disabled>Срок подписки</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} — {money(plan.price_minor, plan.currency)}{plan.stars_price ? ` · ${plan.stars_price} Stars` : ""}</option>)}</select></label><p>После создания откроется защищённая страница оплаты ЮKassa.</p><Button disabled={busy || !plans.some((plan) => plan.id === selected)} type="submit">{busy ? "Подождите…" : "Оплатить через ЮKassa"}<ArrowRight size={17} /></Button></form></section></div>
    <section className="panel orders-panel"><div className="panel-title"><h2>История заказов</h2><Clock3 size={19} /></div>{!orders.length ? <div className="empty-state"><p>У вас пока нет заказов.</p></div> : <div className="table-scroll"><table><thead><tr><th>Заказ</th><th>Тариф</th><th>Сумма</th><th>Статус</th><th>Дата</th><th /></tr></thead><tbody>{orders.map((order) => <tr key={order.id}><td className="order-id">{order.id.slice(0, 8)}</td><td>{order.plan_name}</td><td>{money(order.amount_minor, order.currency)}</td><td><span className={`status-badge status-${order.status}`}>{statuses[order.status]}</span></td><td>{new Date(order.created_at).toLocaleDateString("ru-RU")}</td><td>{order.status === "pending" && <Button variant="outline" onClick={() => payOrder(order)} disabled={busy}>Оплатить</Button>}</td></tr>)}</tbody></table></div>}</section>
  </>;
}
