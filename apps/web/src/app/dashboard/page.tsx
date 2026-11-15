import { Suspense } from "react";
import { Header } from "@/components/header";
import { Account } from "@/components/account";

export default function Dashboard() {
  return <><Header /><main className="wrap account-main"><Suspense fallback={<p>Открываем кабинет…</p>}><Account /></Suspense></main></>;
}
