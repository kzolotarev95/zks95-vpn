export type Plan = {
  id: string; code: string; name: string; description: string;
  price_minor: number; currency: string; duration_days: number; device_limit: number; stars_price?: number | null;
};
export type User = { id: string; email: string; created_at: string };
export type Order = {
  id: string; plan_name: string; amount_minor: number; currency: string;
  status: "pending" | "paid" | "cancelled" | "refunded"; created_at: string; stars_price?: number | null;
};
export type Payment = {
  id: string; order_id: string; provider: string; status: "pending" | "succeeded" | "canceled" | "refunded";
  amount_minor: number; currency: string; confirmation_url?: string | null; created_at: string; paid_at?: string | null;
};
export type Subscription = {
  id: string; plan_name: string; status: string; device_limit: number; expires_at: string;
  connection_url?: string | null; provider_name?: string | null; vpn_status?: string | null; used_bytes?: number | null;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail :
      response.status === 422 ? "Проверьте email и пароль (от 5 символов)." : "Не удалось выполнить запрос.");
  }
  return response.status === 204 ? undefined as T : response.json();
}
