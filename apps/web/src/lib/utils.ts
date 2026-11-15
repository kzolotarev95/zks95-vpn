import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }

export function money(minor: number, currency = "RUB") {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency", currency, maximumFractionDigits: 0,
  }).format(minor / 100);
}
