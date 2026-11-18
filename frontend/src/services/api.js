import { reactive } from "vue";

export const session = reactive({ user: null, loaded: false });
export const API_BASE = "http://localhost:5000/api";

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ message: `Server returned HTTP ${response.status}.` }));
    if (response.status === 401 && path !== "/login") {
      session.user = null;
      if (path !== "/session") window.location.assign("/");
    }
    const error = new Error(payload.message || payload.msg || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function restoreSession() {
  try {
    const result = await api("/session");
    session.user = result.user;
  } catch (error) {
    if (error.status !== 401) throw error;
  }
  session.loaded = true;
}

export function formatDate(value) {
  return value ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "-";
}

export function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export function toISO(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error("Enter all required dates and times.");
  return date.toISOString();
}

export function statusClass(status) {
  if (["Active", "Completed", "Available", "Sent", "Published"].includes(status)) return "text-bg-success";
  if (["Cancelled", "Inactive", "Archived", "Failed"].includes(status)) return "text-bg-danger";
  if (["Booked", "Booking Open", "Submitted"].includes(status)) return "text-bg-primary";
  if (["Full", "Closed", "Slot Creation", "Running", "Queued"].includes(status)) return "text-bg-warning";
  return "text-bg-secondary";
}
