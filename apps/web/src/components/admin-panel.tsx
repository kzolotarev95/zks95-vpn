"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, BadgeCheck, BookOpen, CreditCard, LayoutDashboard, LogOut, Plus, RefreshCw, Send, Settings2, Shield, Users } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Admin = { id: string; email: string; role: string; permissions: string[] };
type Row = Record<string, string | number | boolean | null>;
type BotStatus = { configured: boolean; enabled: boolean; username: string | null; support_username: string | null; connected: boolean; last_seen_at: string | null; last_error: string | null };
type PlanEdit = { id?: string; code: string; name: string; description: string; price_minor: number; duration_days: number; device_limit: number; is_active: boolean };
type Column = { label: string; key: string; render?: (row: Row) => React.ReactNode };
const sections = [
  { key: "overview", label: "Обзор", Icon: LayoutDashboard },
  { key: "users", label: "Пользователи", Icon: Users },
  { key: "orders", label: "Заказы", Icon: CreditCard },
  { key: "subscriptions", label: "Подписки", Icon: BadgeCheck },
  { key: "plans", label: "Тарифы", Icon: Settings2 },
  { key: "telegram", label: "Telegram-бот", Icon: Send },
  { key: "audit", label: "Журнал действий", Icon: BookOpen },
];
const date = (value: unknown) => value ? new Date(String(value)).toLocaleString("ru-RU") : "—";
const labels: Record<string, string> = { pending: "Ожидает оплаты", paid: "Оплачен", cancelled: "Отменён", refunded: "Возврат", active: "Активна", expired: "Истекла", revoked: "Отозвана" };

export function AdminPanel() {
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [ready, setReady] = useState(false);
  const [section, setSection] = useState("overview");
  const [rows, setRows] = useState<Row[]>([]);
  const [overview, setOverview] = useState<Row | null>(null);
  const [bot, setBot] = useState<BotStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [support, setSupport] = useState("");
  const [token, setToken] = useState("");
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [edit, setEdit] = useState<PlanEdit | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    api<Admin>("/admin/me").then(setAdmin).catch((e) => {
      if (!(e instanceof ApiError && e.status === 401)) setError(e.message);
    }).finally(() => setReady(true));
  }, []);

  const load = useCallback(async () => {
    const data = await api<unknown>(`/admin/${section}?offset=${offset}&limit=50${section === "users" ? `&q=${encodeURIComponent(query)}` : ""}`);
    if (section === "overview") setOverview(data as Row);
    else if (section === "telegram") {
      const status = data as BotStatus;
      setBot(status); setEnabled(status.enabled); setSupport(status.support_username || "");
    } else setRows(data as Row[]);
  }, [section, offset, query]);

  useEffect(() => {
    if (!admin) return;
    let cancelled = false;
    const path = `/admin/${section}?offset=${offset}&limit=50${section === "users" ? `&q=${encodeURIComponent(query)}` : ""}`;
    api<unknown>(path).then((data) => {
      if (cancelled) return;
      if (section === "overview") setOverview(data as Row);
      else if (section === "telegram") {
        const status = data as BotStatus;
        setBot(status); setEnabled(status.enabled); setSupport(status.support_username || "");
      } else setRows(data as Row[]);
    }).catch((e) => {
      if (cancelled) return;
      setError(e.message); if (e instanceof ApiError && e.status === 401) setAdmin(null);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [admin, section, offset, query, refresh]);

  useEffect(() => {
    if (!admin || section !== "telegram") return;
    const timer = setInterval(() => {
      api<BotStatus>("/admin/telegram").then(setBot).catch(() => {});
    }, 10000);
    return () => clearInterval(timer);
  }, [admin, section]);

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const user = await api<Admin>("/admin/login", { method: "POST", body: JSON.stringify({ email: form.get("email"), password: form.get("password"), otp: form.get("otp") }) });
      setAdmin(user); setSection("overview"); setLoading(true);
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось войти"); }
    finally { setBusy(false); }
  }

  async function mutate(path: string, method: string, body?: unknown) {
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`/admin${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      if (path === "/logout") { setAdmin(null); return true; }
      await load(); setNotice("Изменения сохранены"); return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
      if (e instanceof ApiError && e.status === 401) setAdmin(null);
      return false;
    } finally { setBusy(false); }
  }

  async function savePlan(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!edit) return;
    const form = new FormData(event.currentTarget);
    const body = { code: form.get("code"), name: form.get("name"), description: form.get("description"), price_minor: Math.round(Number(form.get("price")) * 100), duration_days: Number(form.get("duration")), device_limit: Number(form.get("devices")), is_active: form.get("active") === "on" };
    if (await mutate(edit.id ? `/plans/${edit.id}` : "/plans", edit.id ? "PUT" : "POST", body)) setEdit(null);
  }

  async function saveBot(event: React.FormEvent) {
    event.preventDefault();
    if (await mutate("/telegram", "PUT", { token: token || undefined, enabled, support_username: support.replace(/^@/, "") || null })) setToken("");
  }

  function navigate(next: string) {
    setSection(next); setOffset(0); setRows([]); setError(""); setNotice(""); setEdit(null); setLoading(true); setRefresh((n) => n + 1);
  }

  const can = (permission: string) => !!admin?.permissions.includes(permission);
  let columns: Column[] = [];
  if (section === "users") columns = [
    { key: "email", label: "Аккаунт", render: (r) => <><strong>{r.email || r.display_name || "Telegram"}</strong><small>{String(r.id)}</small></> },
    { key: "telegram_id", label: "Telegram", render: (r) => r.telegram_id ? <>{r.telegram_username ? `@${r.telegram_username}` : "Без username"}<small>{String(r.telegram_id)}</small></> : "—" },
    { key: "role", label: "Роль", render: (r) => r.role || "Пользователь" },
    { key: "is_active", label: "Статус", render: (r) => <span className={r.is_active ? "state-ok" : "state-off"}>{r.is_active ? "Активен" : "Заблокирован"}</span> },
    { key: "created_at", label: "Регистрация", render: (r) => date(r.created_at) },
    { key: "actions", label: "", render: (r) => can("users:write") && r.id !== admin?.id && <Button variant="outline" disabled={busy} onClick={() => mutate(`/users/${r.id}`, "PATCH", { is_active: !r.is_active })}>{r.is_active ? "Заблокировать" : "Разблокировать"}</Button> },
  ];
  if (section === "orders") columns = [
    { key: "id", label: "Заказ", render: (r) => <code>{String(r.id).slice(0, 8)}</code> },
    { key: "email", label: "Пользователь", render: (r) => <>{r.email || "Telegram"}<small>{String(r.user_id).slice(0, 8)}</small></> },
    { key: "plan_name", label: "Тариф" }, { key: "amount_minor", label: "Сумма", render: (r) => money(Number(r.amount_minor)) },
    { key: "status", label: "Статус", render: (r) => <span className={`status-badge status-${r.status}`}>{labels[String(r.status)] || r.status}</span> },
    { key: "created_at", label: "Создан", render: (r) => date(r.created_at) },
  ];
  if (section === "subscriptions") columns = [
    { key: "email", label: "Пользователь", render: (r) => <>{r.email || "Telegram"}<small>{String(r.user_id).slice(0, 8)}</small></> },
    { key: "plan_name", label: "Тариф" }, { key: "device_limit", label: "Устройств" },
    { key: "expires_at", label: "Истекает", render: (r) => date(r.expires_at) },
    { key: "status", label: "Статус", render: (r) => labels[String(r.status)] || r.status },
    { key: "actions", label: "", render: (r) => can("subscriptions:write") && r.status === "active" && <Button variant="outline" disabled={busy} onClick={() => { if (window.confirm("Отозвать эту подписку?")) void mutate(`/subscriptions/${r.id}/revoke`, "POST"); }}>Отозвать</Button> },
  ];
  if (section === "plans") columns = [
    { key: "name", label: "Тариф", render: (r) => <><strong>{r.name}</strong><small>{r.code}</small></> },
    { key: "price_minor", label: "Цена", render: (r) => money(Number(r.price_minor)) },
    { key: "duration_days", label: "Дней" }, { key: "device_limit", label: "Устройств" },
    { key: "is_active", label: "В каталоге", render: (r) => r.is_active ? "Да" : "Нет" },
    { key: "actions", label: "", render: (r) => can("plans:write") && <Button variant="outline" disabled={busy} onClick={() => setEdit(r as unknown as PlanEdit)}>Изменить</Button> },
  ];
  if (section === "audit") columns = [
    { key: "created_at", label: "Время", render: (r) => date(r.created_at) },
    { key: "action", label: "Действие", render: (r) => <code>{r.action}</code> },
    { key: "actor_id", label: "Пользователь", render: (r) => <code title={String(r.actor_id)}>{String(r.actor_id || "system").slice(0, 8)}</code> },
    { key: "target_id", label: "Объект", render: (r) => <code title={String(r.target_id)}>{String(r.target_id || "—").slice(0, 12)}</code> },
  ];

  if (!ready) return <main className="empty-state admin-wait" aria-busy="true">Открываем управление сервисом…</main>;
  if (!admin) return <main className="admin-auth"><Link href="/" className="brand"><Shield size={25} />ZKS95<span className="brand-vpn">CONTROL</span></Link><section className="auth-card"><div className="eyebrow">УПРАВЛЕНИЕ СЕРВИСОМ</div><h2>Вход администратора</h2><p>Личный доступ с подтверждением 2FA.</p><form onSubmit={login}><label>Email<input name="email" type="email" autoComplete="username" required maxLength={254} /></label><label>Пароль<input name="password" type="password" autoComplete="current-password" required minLength={12} maxLength={128} /></label><label>Код из приложения-аутентификатора<input name="otp" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" required placeholder="000000" /></label>{error && <p className="form-error" role="alert">{error}</p>}<Button disabled={busy} type="submit">{busy ? "Проверяем…" : "Войти в панель"}<ArrowRight size={16} /></Button></form><p className="auth-note">Первый администратор создаётся командой на сервере. Общего логина и пароля нет.</p></section><Link href="/" className="text-link"><ArrowLeft size={14} /> Вернуться на сайт</Link></main>;

  const title = sections.find((item) => item.key === section)?.label;
  return <div className="admin-layout"><aside className="admin-sidebar"><Link href="/" className="brand"><Shield size={25} />ZKS95<span className="brand-vpn">CONTROL</span></Link><div className="sidebar-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div><nav>{sections.filter((item) => can(item.key)).map(({ key, label, Icon }) => <button key={key} className={key === section ? "active" : ""} onClick={() => navigate(key)}><Icon size={17} />{label}{key === section && <span />}</button>)}</nav><div className="admin-identity"><span className="tag">{admin.role}</span><p>{admin.email}</p><button disabled={busy} onClick={async () => { if (await mutate("/logout", "POST")) setAdmin(null); }}><LogOut size={15} /> Выйти</button></div></aside>
    <main className="admin-content"><header className="admin-topbar"><span><span className="gold-dot" /> ZKS95 VPN / УПРАВЛЕНИЕ</span><Link href="/dashboard">Личный кабинет <ArrowRight size={13} /></Link></header><div className="admin-heading"><div><div className="eyebrow">CONTROL CENTER</div><h1>{title}<span>.</span></h1></div><Button variant="outline" disabled={busy || loading} onClick={() => { setLoading(true); setError(""); setRefresh((n) => n + 1); }}><RefreshCw size={15} />Обновить</Button></div>
      {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="form-success" role="status">{notice}</p>}
      {section === "overview" && overview && <><div className="admin-metrics">{[
        ["Пользователи", overview.users, "Включая Telegram"], ["Telegram", overview.telegram_users, "Привязанные аккаунты"], ["Заказы", overview.orders, `Ожидают оплаты: ${overview.pending_orders}`], ["Активные подписки", overview.active_subscriptions, "По текущему сроку"], ["Оплачено", money(Number(overview.revenue_minor)), "Подтверждённые заказы"],
      ].map(([label, value, detail]) => <article key={String(label)}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>)}</div><section className="panel admin-overview-note"><Activity size={24} /><div><h2>Ваш сервис под контролем</h2><p>Пользователи, заказы и тарифы показывают данные общей базы. Подключите бота в разделе Telegram. Платежи и VPN-ноды добавляются следующим этапом; их статистика пока недоступна.</p></div></section></>}
      {section === "users" && <form className="admin-search" onSubmit={(e) => { e.preventDefault(); setQuery(search); setOffset(0); setLoading(true); setRefresh((n) => n + 1); }}><input aria-label="Поиск пользователей" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Email, Telegram username или ID" maxLength={254} /><Button type="submit" variant="outline">Найти</Button></form>}
      {section === "plans" && can("plans:write") && !edit && <Button className="admin-add-plan" onClick={() => setEdit({ code: "", name: "", description: "", price_minor: 19900, duration_days: 30, device_limit: 3, is_active: true })}><Plus size={16} />Новый тариф</Button>}
      {section === "plans" && edit && <section className="panel admin-editor"><h2>{edit.id ? "Изменить тариф" : "Новый тариф"}</h2><form onSubmit={savePlan} key={edit.id || "new"}><label>Код<input name="code" defaultValue={edit.code} pattern="[a-z0-9_-]{2,32}" required /></label><label>Название<input name="name" defaultValue={edit.name} required maxLength={100} /></label><label className="full-field">Описание<input name="description" defaultValue={edit.description} required maxLength={2000} /></label><label>Цена, ₽<input name="price" type="number" min="0.01" max="1000000" step="0.01" defaultValue={edit.price_minor / 100} required /></label><label>Длительность, дней<input name="duration" type="number" min={1} max={3650} defaultValue={edit.duration_days} required /></label><label>Устройств<input name="devices" type="number" min={1} max={100} defaultValue={edit.device_limit} required /></label><label className="checkbox-label"><input name="active" type="checkbox" defaultChecked={edit.is_active} /> Показывать в каталоге</label><div className="editor-actions"><Button type="submit" disabled={busy}>Сохранить</Button><Button type="button" variant="outline" onClick={() => setEdit(null)}>Отмена</Button></div></form><p>Ранее созданные заказы сохраняют свою цену и условия.</p></section>}
      {columns.length > 0 && <section className="panel admin-table"><div className="table-scroll"><table aria-label={title}><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={String(row.id)}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : String(row[column.key] ?? "—")}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="empty-state">{loading ? "Загружаем…" : "Записей пока нет"}</div>}</div>{section !== "plans" && <div className="pagination"><span>Записи {rows.length ? offset + 1 : 0}–{offset + rows.length}</span><Button variant="outline" disabled={!offset || loading} onClick={() => { setOffset(Math.max(0, offset - 50)); setLoading(true); }}>Назад</Button><Button variant="outline" disabled={rows.length < 50 || loading} onClick={() => { setOffset(offset + 50); setLoading(true); }}>Далее</Button></div>}</section>}
      {section === "telegram" && bot && <div className="telegram-grid"><section className="panel bot-settings"><div className="panel-title"><h2>Подключение бота</h2><Send size={20} /></div><p>Создайте бота через <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> и вставьте токен ниже. После сохранения он хранится зашифрованным и больше не показывается.</p><form onSubmit={saveBot}><label>Токен BotFather<input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} maxLength={256} placeholder={bot.configured ? "Сохранён. Оставьте пустым, чтобы не менять" : "123456789:…"} required={!bot.configured} /></label><label>Поддержка в Telegram<input value={support} onChange={(e) => setSupport(e.target.value)} placeholder="@username — необязательно" maxLength={33} /></label><label className="checkbox-label"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Включить бота</label><Button type="submit" disabled={busy}>{busy ? "Проверяем Telegram…" : "Сохранить настройки"}<ArrowRight size={16} /></Button></form></section><section className="panel bot-status"><div className="panel-title"><h2>Состояние</h2><Activity size={19} /></div><div className={`bot-indicator ${bot.connected ? "online" : ""}`}><span />{bot.connected ? "Бот отвечает на запросы Telegram" : bot.enabled ? "Ожидаем подключения" : "Бот выключен"}</div><dl><div><dt>Бот</dt><dd>{bot.username ? <a href={`https://t.me/${bot.username}`} target="_blank" rel="noreferrer">@{bot.username} ↗</a> : "Не подключён"}</dd></div><div><dt>Последний ответ</dt><dd>{date(bot.last_seen_at)}</dd></div></dl>{bot.last_error && <p className="form-error">{bot.last_error === "telegram_conflict" ? "Бот запущен ещё в одном сервисе. Остановите другой экземпляр." : bot.last_error === "telegram_unauthorized" ? "Telegram отклонил сохранённый токен. Укажите новый токен BotFather." : "Соединение с Telegram временно недоступно."}</p>}<p>Работают меню, аккаунты, тарифы, заказы и просмотр подписок. Оплата и VPN-конфигурации пока недоступны.</p><small>Статус обновляется каждые 10 секунд. Для одного токена должен работать один экземпляр бота.</small></section></div>}
    </main></div>;
}
