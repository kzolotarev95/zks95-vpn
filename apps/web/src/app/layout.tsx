import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZKS95 VPN — ваше личное пространство",
  description: "ZKS95 VPN. Личный защищённый доступ, понятные подписки и единый кабинет. Сервис готовится к запуску.",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  await headers();
  return <html lang="ru"><body>{children}</body></html>;
}
