// flight-watch: email sign-up + price-drop emails for FRA⇄Tokyo (2027/7/25–8/13)
//   POST ?action=subscribe   {email}      -> stores the address, sends a welcome email
//   GET  ?action=unsubscribe&token=...    -> removes the address
//   POST ?action=notify                   -> emails every subscriber about new rows in history.json
// Emails are delivered through ntfy.sh's email forwarding (no mail account needed).
import { createClient } from "npm:@supabase/supabase-js@2";

const REPO = "tetsuyat3333-web/flight-watch";
const SITE = "https://tetsuyat3333-web.github.io/flight-watch/";
const FN_URL = `${Deno.env.get("SUPABASE_URL")}/functions/v1/fw`;
const MAX_SUBSCRIBERS = 50;

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, authorization, apikey, x-client-info",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
const html = (text: string) =>
  new Response(`<!DOCTYPE html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:sans-serif;padding:32px;text-align:center"><p>${text}</p><p><a href="${SITE}">Back to the site</a></p>`, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });

async function sendEmail(to: string, title: string, message: string, click?: string) {
  const res = await fetch("https://ntfy.sh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic: "fw-" + crypto.randomUUID().slice(0, 12),
      title,
      message,
      email: to,
      tags: ["airplane"],
      ...(click ? { click } : {}),
    }),
  });
  if (!res.ok) throw new Error(`ntfy ${res.status}: ${(await res.text()).slice(0, 200)}`);
}

async function repoJson(path: string) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}?ref=main`, {
    headers: { Accept: "application/vnd.github.raw+json", "User-Agent": "flight-watch" },
  });
  if (!r.ok) throw new Error(`github ${r.status}`);
  return r.json();
}

const fmt = (f: any) =>
  f ? `€${f.price} ${f.airlines.join("/")} ${f.dep_airport}→${f.arr_airport} ${f.stops ? `${f.stops} stop(s)` : "nonstop"}` : "—";

async function subscribe(req: Request) {
  const { email } = await req.json().catch(() => ({}));
  const e = String(email || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e) || e.length > 254) return json({ ok: false, error: "Please enter a valid email address" }, 400);

  const { data: existing } = await db.from("fw_subscribers").select("id").eq("email", e).maybeSingle();
  if (existing) return json({ ok: true, already: true });

  const { count } = await db.from("fw_subscribers").select("id", { count: "exact", head: true });
  if ((count ?? 0) >= MAX_SUBSCRIBERS) return json({ ok: false, error: "The subscriber limit has been reached" }, 429);

  const { data, error } = await db.from("fw_subscribers").insert({ email: e }).select("token").single();
  if (error) return json({ ok: false, error: "Could not subscribe" }, 500);

  let now = "";
  try {
    const latest = await repoJson("data/latest.json");
    now = `\n\nLowest fares right now\nOverall: ${fmt(latest.best)}\nNonstop: ${fmt(latest.nonstop)}`;
  } catch (_) { /* optional */ }
  try {
    await sendEmail(
      e,
      "✈️ You are subscribed to FRA⇄Tokyo fare alerts",
      `We will email you when the cheapest overall or cheapest nonstop round-trip fare for 25 Jul – 13 Aug 2027 drops.${now}\n\nSite: ${SITE}\nUnsubscribe: ${FN_URL}?action=unsubscribe&token=${data.token}`,
      SITE,
    );
  } catch (err) {
    return json({ ok: true, warning: "Subscribed, but the confirmation email could not be sent", detail: String(err) });
  }
  return json({ ok: true });
}

async function unsubscribe(url: URL) {
  const token = url.searchParams.get("token") || "";
  if (!/^[0-9a-f-]{36}$/i.test(token)) return html("This link is not valid.");
  await db.from("fw_subscribers").delete().eq("token", token);
  return html("You have been unsubscribed.");
}

async function notify() {
  const history: any[] = await repoJson("data/history.json");
  const { data: st } = await db.from("fw_state").select("value").eq("key", "last_notified").maybeSingle();
  const last = st?.value || "";
  const latestT = history.length ? history[history.length - 1].t : "";

  if (!last) {
    // first run: start from now, do not replay old rows
    await db.from("fw_state").upsert({ key: "last_notified", value: latestT });
    return json({ ok: true, initialized: latestT });
  }

  const pending = history.filter((h) => h.t > last && h.notify);
  if (latestT > last) await db.from("fw_state").upsert({ key: "last_notified", value: latestT });
  if (!pending.length) return json({ ok: true, sent: 0 });

  const { data: subs } = await db.from("fw_subscribers").select("email, token");
  const n = pending[pending.length - 1].notify; // newest message only
  let sent = 0;
  const errors: string[] = [];
  for (const s of subs ?? []) {
    try {
      await sendEmail(s.email, n.title, `${n.message}\n\nBook on Skyscanner: ${n.click}\nSite: ${SITE}\nUnsubscribe: ${FN_URL}?action=unsubscribe&token=${s.token}`, n.click);
      sent++;
    } catch (err) {
      errors.push(String(err).slice(0, 120));
    }
  }
  return json({ ok: true, sent, errors });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  const url = new URL(req.url);
  const action = url.searchParams.get("action");
  try {
    if (action === "subscribe" && req.method === "POST") return await subscribe(req);
    if (action === "unsubscribe") return await unsubscribe(url);
    if (action === "notify" && req.method === "POST") return await notify();
    return json({ ok: false, error: "unknown action" }, 404);
  } catch (err) {
    return json({ ok: false, error: String(err).slice(0, 200) }, 500);
  }
});
