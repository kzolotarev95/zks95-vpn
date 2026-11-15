"use client";

import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function TelegramLink() {
  const [status, setStatus] = useState<{ linked: boolean; username: string | null; bot_username: string | null } | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<typeof status>("/me/telegram").then(setStatus).catch(() => {}); }, []);
  if (!status?.bot_username) return null;
  return <section className="panel account-telegram"><Send size={22} /><div><h3>Ваш аккаунт в Telegram</h3><p>{status.linked ? `Подключён: ${status.username ? `@${status.username}` : "Telegram"}` : "Откройте персональную ссылку, чтобы пользоваться этим аккаунтом в боте."}</p>{error && <p className="form-error" role="alert">{error}</p>}</div>{status.linked ? <Button asChild variant="outline"><a href={`https://t.me/${status.bot_username}`} target="_blank" rel="noreferrer">Открыть бота</a></Button> : url ? <Button asChild><a href={url} target="_blank" rel="noreferrer">Перейти в Telegram</a></Button> : <Button disabled={busy} onClick={async () => {
    setBusy(true); setError("");
    try { const result = await api<{ url: string }>("/me/telegram-link", { method: "POST" }); setUrl(result.url); }
    catch (e) { setError(e instanceof Error ? e.message : "Ошибка подключения"); }
    finally { setBusy(false); }
  }}>Подключить Telegram</Button>}</section>;
}
