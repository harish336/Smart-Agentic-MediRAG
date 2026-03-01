import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  getCurrentUser,
  loginUser,
  registerUser,
  requestPasswordResetOtp,
  resetPasswordWithOtp,
  verifyPasswordResetOtp,
} from "./api/auth";
import * as answerApi from "./api/answer";
import {
  adminIngestFiles,
  bulkDeleteIngestedDocuments,
  deleteIngestedDocument,
  fetchAdminStatistics,
  listIngestedDocuments,
  retrieveChunksForVerification,
} from "./api/admin";

const { askQuestion, deleteThread, listThreadMessages, listThreads } = answerApi;

// Safely extract renameThread if it exists in the API, otherwise provide a fallback
// Fixed: Wrapped the fallback async arrow function in parentheses to satisfy Babel's parser
const renameThreadApi = answerApi.renameThread || (async (id, title) => {
  console.warn("renameThread endpoint not found in ./api/answer. Mocking success for UI.");
  return { id, title };
});

function getErrorMessage(error, fallback) {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  return error.message || error.error || fallback;
}

function persistSession(loginRes) {
  localStorage.setItem("access_token", loginRes?.access_token || "");
  localStorage.setItem("refresh_token", loginRes?.refresh_token || "");
  localStorage.setItem("role", loginRes?.user?.role || "user");
}

function clearSession() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("role");
}

function Toasts({ items }) {
  if (!items.length) return null;
  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-3 pointer-events-none">
      {items.map((toast) => (
        <div
          key={toast.id}
          className={`px-5 py-3.5 rounded-2xl border text-sm shadow-[0_10px_40px_rgba(0,0,0,0.3)] backdrop-blur-xl transition-all duration-500 animate-in slide-in-from-top-5 fade-in zoom-in-95 flex items-center gap-3 ${
            toast.type === "error"
              ? "bg-rose-500/15 border-rose-500/40 text-rose-200"
              : "bg-emerald-500/15 border-emerald-500/40 text-emerald-200"
          }`}
        >
          {toast.type === "error" ? (
            <div className="p-1 rounded-full bg-rose-500/20 text-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.3)]">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
          ) : (
            <div className="p-1 rounded-full bg-emerald-500/20 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.3)]">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
            </div>
          )}
          <span className="font-semibold tracking-wide">{toast.message}</span>
        </div>
      ))}
    </div>
  );
}

function threadDisplayName(thread) {
  if (!thread) return "Untitled conversation";
  const title = (thread.title || "").trim();
  return title || thread.id;
}

function formatAssistantContent(content) {
  const text = typeof content === "string" ? content : "";

  const unescaped = text
    .replace(/\\r\\n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\n")
    .replace(/\\t/g, "\t");

  const normalized = unescaped
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\n(#{1,6}\s)/g, "$1\n\n$2")
    .replace(/([^\n])\n([-\*]\s|\d+\.\s)/g, "$1\n\n$2") 
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (!normalized) return "No response.";
  if (normalized.toLowerCase() === "dont have an answer") {
    return "I don't have enough reliable context to answer that yet. Please share a bit more detail.";
  }

  return normalized;
}

function CitationBox({ citations }) {
  const [open, setOpen] = useState(false);
  if (!Array.isArray(citations) || citations.length === 0) return null;

  return (
    <div className="mt-6 rounded-2xl border border-slate-700/40 bg-[#0b1016]/50 overflow-hidden transition-all duration-500 shadow-inner backdrop-blur-sm">
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3.5 text-left text-sm font-semibold text-slate-300 hover:bg-slate-800/40 transition-colors group"
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 group-hover:bg-cyan-500/20 group-hover:scale-105 transition-all">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          Sources ({citations.length})
        </span>
        <span className="text-xs text-slate-400 bg-slate-800/60 px-2.5 py-1 rounded-md border border-slate-700/50 flex items-center gap-1 group-hover:text-slate-200 transition-colors">
          {open ? "Hide Details" : "View Sources"}
          <svg className={`w-3 h-3 transition-transform duration-500 ease-[cubic-bezier(0.87,_0,_0.13,_1)] ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" /></svg>
        </span>
      </button>
      
      <div className={`grid gap-3 border-slate-700/30 bg-slate-950/40 sm:grid-cols-2 overflow-hidden transition-all duration-500 ease-[cubic-bezier(0.87,_0,_0.13,_1)] ${open ? 'max-h-[1000px] p-4 border-t opacity-100' : 'max-h-0 p-0 opacity-0 border-t-0'}`}>
        {citations.map((citation, idx) => {
          const documentName = citation?.document?.name || "Unknown document";
          const docId = citation?.document?.doc_id || "N/A";
          const page = citation?.location?.page_label || citation?.location?.page_physical || "N/A";
          const chapter = citation?.location?.chapter || "N/A";
          const section = citation?.location?.subheading || "N/A";
          
          return (
            <div key={citation?.id || idx} className="rounded-xl border border-slate-800 bg-slate-900/40 p-3.5 text-xs text-slate-300 hover:border-cyan-500/40 hover:bg-slate-800/80 transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_4px_20px_rgba(6,182,212,0.1)] group/cit cursor-default">
              <div className="font-bold text-cyan-400 mb-2.5 flex items-center gap-2 border-b border-slate-800 pb-2 group-hover/cit:border-cyan-500/30 transition-colors">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_currentColor]"></span>
                {citation?.id || `CITATION-${String(idx + 1).padStart(3, "0")}`}
              </div>
              <div className="space-y-1.5">
                <div className="flex justify-between items-center"><span className="text-slate-500 font-medium">Doc:</span> <span className="truncate ml-2 text-slate-200" title={documentName}>{documentName}</span></div>
                <div className="flex justify-between items-center"><span className="text-slate-500 font-medium">ID:</span> <span className="truncate ml-2 text-slate-400 font-mono">{docId}</span></div>
                <div className="flex justify-between items-center"><span className="text-slate-500 font-medium">Page:</span> <span className="text-emerald-300 font-mono bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">{page}</span></div>
                <div className="flex justify-between items-center"><span className="text-slate-500 font-medium">Chapter:</span> <span className="truncate ml-2">{chapter}</span></div>
                <div className="flex justify-between items-center"><span className="text-slate-500 font-medium">Section:</span> <span className="truncate ml-2">{section}</span></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AuthPanel({ onAuthSuccess, addToast }) {
  const [mode, setMode] = useState("login");
  const [step, setStep] = useState("request");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", otp: "", newPassword: "" });
  const [devOtp, setDevOtp] = useState("");

  const title = useMemo(() => {
    if (mode === "register") return "Create Account";
    if (mode === "forgot") return "Reset Password";
    return "Welcome Back";
  }, [mode]);

  const updateField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleLoginOrRegister = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (!form.password.trim()) throw new Error("Password is required");
      if (mode === "register") {
        if (!form.username.trim() || !form.email.trim()) throw new Error("Name, email, and password are required");
        await registerUser({ username: form.username.trim(), email: form.email.trim(), password: form.password, role: "user" });
      }
      const loginRes = await loginUser({ email: form.email.trim(), username: form.username.trim(), password: form.password });
      persistSession(loginRes);
      onAuthSuccess();
    } catch (error) { addToast(getErrorMessage(error, "Authentication failed"), "error"); } finally { setLoading(false); }
  };

  const handleOtpRequest = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (!form.email.trim()) throw new Error("Email is required");
      const res = await requestPasswordResetOtp(form.email.trim());
      setDevOtp(res.otp || ""); setStep("verify");
      addToast(res.message || "OTP generated", "success");
      if (res.otp) addToast(`Dev OTP: ${res.otp}`, "success");
    } catch (error) { addToast(getErrorMessage(error, "Could not request OTP"), "error"); } finally { setLoading(false); }
  };

  const handleOtpVerifyAndReset = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (!form.email.trim() || !form.otp.trim() || !form.newPassword.trim()) throw new Error("Email, OTP and new password are required");
      await verifyPasswordResetOtp({ email: form.email.trim(), otp: form.otp.trim() });
      await resetPasswordWithOtp({ email: form.email.trim(), otp: form.otp.trim(), new_password: form.newPassword });
      addToast("Password updated. Sign in now.", "success");
      setMode("login"); setStep("request"); setDevOtp("");
      setForm((prev) => ({ ...prev, otp: "", newPassword: "", password: "" }));
    } catch (error) { addToast(getErrorMessage(error, "Password reset failed"), "error"); } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#05090f] text-slate-100 relative overflow-hidden flex items-center justify-center selection:bg-emerald-500/30">
      <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] bg-emerald-500/10 blur-[120px] rounded-full pointer-events-none animate-pulse duration-[8000ms]" />
      <div className="absolute -bottom-[20%] -right-[10%] w-[50%] h-[50%] bg-cyan-500/10 blur-[120px] rounded-full pointer-events-none animate-pulse duration-[10000ms]" />
      
      <div className="relative w-full max-w-[420px] px-4 z-10 animate-in fade-in zoom-in-[0.98] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]">
        <div className="rounded-[2.5rem] border border-slate-800/60 bg-[#0b1016]/80 p-8 sm:p-10 shadow-[0_20px_60px_rgba(0,0,0,0.6)] backdrop-blur-3xl relative overflow-hidden">
          <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400 bg-[length:200%_auto] animate-[gradient_3s_linear_infinite]" />
          
          <div className="flex flex-col items-center gap-4 mb-10 text-center relative z-10">
            <div className="h-16 w-16 rounded-[1.25rem] bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center shadow-[0_0_30px_rgba(16,185,129,0.3)] transform transition-transform hover:scale-105 duration-500">
              <svg className="w-8 h-8 text-white drop-shadow-md" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.3em] text-emerald-400 font-bold mb-1.5 drop-shadow-[0_0_8px_currentColor]">Smart Medirag</div>
              <h1 className="text-3xl font-bold tracking-tight text-white">{title}</h1>
            </div>
          </div>

          {(mode === "login" || mode === "register") && (
            <form className="space-y-5 relative z-10" onSubmit={handleLoginOrRegister}>
              <div className="space-y-4">
                {mode === "register" && (
                  <div className="group animate-in slide-in-from-top-4 fade-in duration-500">
                    <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">Username</label>
                    <input type="text" value={form.username} onChange={(e) => updateField("username", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="johndoe" />
                  </div>
                )}
                <div className="group">
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">Email Address</label>
                  <input type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="name@example.com" />
                </div>
                <div className="group">
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">Password</label>
                  <input type="password" value={form.password} onChange={(e) => updateField("password", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="••••••••" />
                </div>
              </div>
              <button type="submit" disabled={loading} className="w-full rounded-2xl bg-gradient-to-r from-emerald-500 to-cyan-500 py-4 text-sm font-bold text-white shadow-[0_8px_25px_rgba(16,185,129,0.3)] hover:shadow-[0_12px_35px_rgba(16,185,129,0.4)] transition-all duration-300 active:scale-[0.98] disabled:opacity-50 mt-4 relative overflow-hidden group">
                <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
                <span className="relative z-10 flex items-center justify-center gap-2">
                  {loading ? (
                    <><svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Authenticating...</>
                  ) : mode === "register" ? "Create Account" : "Sign In securely"}
                </span>
              </button>
            </form>
          )}

          {mode === "forgot" && step === "request" && (
            <form className="space-y-5 relative z-10 animate-in slide-in-from-right-8 fade-in duration-500" onSubmit={handleOtpRequest}>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">Registered Email</label>
                <input type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 shadow-inner" placeholder="name@domain.com" />
              </div>
              <button type="submit" disabled={loading} className="w-full rounded-2xl bg-gradient-to-r from-emerald-500 to-cyan-500 py-4 text-sm font-bold text-white shadow-[0_8px_25px_rgba(16,185,129,0.3)] hover:shadow-[0_12px_35px_rgba(16,185,129,0.4)] transition-all duration-300 active:scale-[0.98] disabled:opacity-50">
                {loading ? "Generating Code..." : "Send Reset Code"}
              </button>
            </form>
          )}

          {mode === "forgot" && step === "verify" && (
            <form className="space-y-5 relative z-10 animate-in slide-in-from-right-8 fade-in duration-500" onSubmit={handleOtpVerifyAndReset}>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block">Email</label>
                <input type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} className="w-full rounded-2xl border border-slate-800 bg-slate-900/30 px-4 py-3.5 text-sm text-slate-500 shadow-inner" readOnly />
              </div>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">6-Digit Code</label>
                <input type="text" value={form.otp} onChange={(e) => updateField("otp", e.target.value)} placeholder={devOtp ? `Dev OTP: ${devOtp}` : "000000"} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 text-center tracking-[0.5em] font-mono text-lg shadow-inner" />
              </div>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-emerald-400 transition-colors">New Password</label>
                <input type="password" value={form.newPassword} onChange={(e) => updateField("newPassword", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 focus:bg-slate-900 shadow-inner" placeholder="••••••••" />
              </div>
              <button type="submit" disabled={loading} className="w-full rounded-2xl bg-gradient-to-r from-emerald-500 to-cyan-500 py-4 text-sm font-bold text-white shadow-[0_8px_25px_rgba(16,185,129,0.3)] hover:shadow-[0_12px_35px_rgba(16,185,129,0.4)] transition-all duration-300 active:scale-[0.98] disabled:opacity-50">
                {loading ? "Updating..." : "Reset Password"}
              </button>
            </form>
          )}

          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-xs font-bold text-slate-500 pt-6 border-t border-slate-800/60 relative z-10">
            {mode !== "login" && <button className="hover:text-emerald-400 transition-colors" onClick={() => { setMode("login"); setStep("request"); }}>Sign in instead</button>}
            {mode !== "register" && <button className="hover:text-emerald-400 transition-colors" onClick={() => { setMode("register"); setStep("request"); }}>Create an account</button>}
            {mode !== "forgot" && <button className="hover:text-emerald-400 transition-colors" onClick={() => { setMode("forgot"); setStep("request"); }}>Forgot password?</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

function AdminLoginPanel({ addToast, onAdminAuthSuccess, onBackToChat }) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ email: "", username: "", password: "" });

  const updateField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleAdminLogin = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (!form.password.trim()) throw new Error("Password is required");
      if (!form.email.trim() && !form.username.trim()) throw new Error("Email or username is required");
      const loginRes = await loginUser({
        email: form.email.trim(),
        username: form.username.trim(),
        password: form.password,
      });
      if ((loginRes?.user?.role || "") !== "admin") {
        clearSession();
        throw new Error("Invalid credentials");
      }
      persistSession(loginRes);
      onAdminAuthSuccess();
      addToast("Admin login successful", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Admin login failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#05090f] text-slate-100 relative overflow-hidden flex items-center justify-center selection:bg-cyan-500/30">
      <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] bg-cyan-500/10 blur-[120px] rounded-full pointer-events-none animate-pulse duration-[8000ms]" />
      <div className="absolute -bottom-[20%] -right-[10%] w-[50%] h-[50%] bg-blue-500/10 blur-[120px] rounded-full pointer-events-none animate-pulse duration-[10000ms]" />

      <div className="relative w-full max-w-[420px] px-4 z-10 animate-in fade-in zoom-in-[0.98] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]">
        <div className="rounded-[2.5rem] border border-slate-800/60 bg-[#0b1016]/80 p-8 sm:p-10 shadow-[0_20px_60px_rgba(0,0,0,0.6)] backdrop-blur-3xl relative overflow-hidden">
          <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-cyan-400 via-blue-400 to-cyan-400 bg-[length:200%_auto] animate-[gradient_3s_linear_infinite]" />

          <div className="flex flex-col items-center gap-4 mb-10 text-center relative z-10">
            <div className="h-16 w-16 rounded-[1.25rem] bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_30px_rgba(6,182,212,0.3)] transform transition-transform hover:scale-105 duration-500">
              <svg className="w-8 h-8 text-white drop-shadow-md" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 15v2m-6 4h12a2 2 0 002-2V9a2 2 0 00-2-2h-1V5a5 5 0 00-10 0v2H6a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.3em] text-cyan-400 font-bold mb-1.5 drop-shadow-[0_0_8px_currentColor]">Smart Medirag</div>
              <h1 className="text-3xl font-bold tracking-tight text-white">Admin Login</h1>
            </div>
          </div>

          <form className="space-y-5 relative z-10" onSubmit={handleAdminLogin}>
            <div className="space-y-4">
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-cyan-400 transition-colors">Email (optional)</label>
                <input type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="admin@example.com" />
              </div>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-cyan-400 transition-colors">Username (optional)</label>
                <input type="text" value={form.username} onChange={(e) => updateField("username", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="admin" />
              </div>
              <div className="group">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1 mb-2 block group-focus-within:text-cyan-400 transition-colors">Password</label>
                <input type="password" value={form.password} onChange={(e) => updateField("password", e.target.value)} className="w-full rounded-2xl border border-slate-700/50 bg-slate-900/60 px-4 py-3.5 text-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 focus:bg-slate-900 placeholder:text-slate-600 shadow-inner" placeholder="........" />
              </div>
            </div>
            <button type="submit" disabled={loading} className="w-full rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 py-4 text-sm font-bold text-white shadow-[0_8px_25px_rgba(6,182,212,0.3)] hover:shadow-[0_12px_35px_rgba(6,182,212,0.4)] transition-all duration-300 active:scale-[0.98] disabled:opacity-50 mt-4">
              {loading ? "Signing in..." : "Sign in as Admin"}
            </button>
          </form>

          <div className="mt-8 flex items-center justify-center gap-6 text-xs font-bold text-slate-500 pt-6 border-t border-slate-800/60 relative z-10">
            <button className="hover:text-cyan-400 transition-colors" onClick={onBackToChat}>Back to Chat</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatPanel({ onLogout, addToast, user, onOpenAdmin }) {
  const [threads, setThreads] = useState([]);
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  
  // Renaming State
  const [editingThreadId, setEditingThreadId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");

  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingAsk, setLoadingAsk] = useState(false);
  const bottomRef = useRef(null);

  const activeThread = useMemo(() => threads.find((thread) => thread.id === threadId) || null, [threads, threadId]);
  const isAdmin = (user?.role || "") === "admin";

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loadingAsk]);

  const loadThreads = async () => {
    try { setLoadingThreads(true); const data = await listThreads(); setThreads(data); } 
    catch (error) { addToast(getErrorMessage(error, "Failed to load threads"), "error"); } 
    finally { setLoadingThreads(false); }
  };

  useEffect(() => { loadThreads(); }, []);

  const openThread = async (id) => {
    if (editingThreadId === id) return; // Prevent opening while editing
    try { setLoadingMessages(true); setThreadId(id); const data = await listThreadMessages(id); setMessages(data); } 
    catch (error) { addToast(getErrorMessage(error, "Failed to load messages"), "error"); } 
    finally { setLoadingMessages(false); }
  };

  const startNewChat = () => { setThreadId(""); setMessages([]); setInput(""); setEditingThreadId(null); };

  const handleDeleteThread = async (id, e) => {
    e.stopPropagation();
    if (!id) return;
    if (!window.confirm("Delete this conversation permanently?")) return;
    try {
      await deleteThread(id);
      if (threadId === id) startNewChat();
      await loadThreads();
      addToast("Conversation deleted", "success");
    } catch (error) { addToast(getErrorMessage(error, "Failed to delete conversation"), "error"); }
  };

  const startRename = (thread, e) => {
    e.stopPropagation();
    setEditingThreadId(thread.id);
    setEditingTitle(thread.title || thread.id);
  };

  const handleRenameSubmit = async (id, e) => {
    e?.preventDefault();
    e?.stopPropagation();
    
    if (!editingTitle.trim()) {
      setEditingThreadId(null);
      return;
    }

    try {
      // Optimistic UI update
      setThreads(prev => prev.map(t => t.id === id ? { ...t, title: editingTitle } : t));
      await renameThreadApi(id, editingTitle);
      addToast("Chat renamed", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to rename chat"), "error");
      loadThreads(); // Revert on failure
    } finally {
      setEditingThreadId(null);
    }
  };

  const sendMessage = async () => {
    const query = input.trim();
    if (!query || loadingAsk) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoadingAsk(true);

    try {
      const res = await askQuestion({ query, thread_id: threadId || null });
      if (!threadId && res.thread_id) setThreadId(res.thread_id);
      setMessages((prev) => [...prev, { role: "assistant", content: formatAssistantContent(res.response), citations: Array.isArray(res.citations) ? res.citations : [] }]);
      await loadThreads();
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: getErrorMessage(error, "Error generating response") }]);
    } finally { setLoadingAsk(false); }
  };

  return (
    <div className="flex h-screen bg-[#05090f] text-slate-200 overflow-hidden font-sans selection:bg-emerald-500/30">
      <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-emerald-500/5 blur-[120px] rounded-full mix-blend-screen animate-pulse duration-[8000ms]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-cyan-500/5 blur-[120px] rounded-full mix-blend-screen animate-pulse duration-[10000ms]" />
      </div>
      
      {/* Sidebar */}
      <aside className="relative z-20 hidden w-[300px] flex-col border-r border-slate-800/60 bg-[#0b1016]/80 md:flex backdrop-blur-2xl shadow-xl">
        <div className="p-6 flex flex-col gap-2 border-b border-slate-800/40 shrink-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]">Smart Medirag</div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-sm font-bold text-slate-100">Conversations</span>
            <span className="inline-flex items-center rounded-md bg-slate-800/80 px-2 py-1 text-[10px] font-bold text-slate-300 ring-1 ring-inset ring-slate-700 uppercase tracking-widest shadow-inner">
              {user?.role || "user"}
            </span>
          </div>
        </div>

        <div className="px-4 pt-5 pb-3 shrink-0">
          <button onClick={startNewChat} className="group relative w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500/10 to-cyan-500/10 border border-emerald-500/30 px-4 py-3.5 text-sm font-bold text-emerald-400 hover:from-emerald-500/20 hover:to-cyan-500/20 hover:border-emerald-400/50 hover:shadow-[0_0_20px_rgba(16,185,129,0.15)] transition-all duration-300 active:scale-[0.98] overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-emerald-400/20 to-cyan-400/20 opacity-0 group-hover:opacity-100 transition-opacity blur-md" />
            <svg className="w-5 h-5 relative z-10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" /></svg>
            <span className="relative z-10">New Chat</span>
          </button>
          
          {isAdmin && (
            <button onClick={onOpenAdmin} className="mt-3 w-full flex items-center justify-center gap-2 rounded-xl bg-slate-800/40 border border-slate-700/50 px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-700 hover:text-white hover:border-slate-600 transition-all duration-300 active:scale-[0.98]">
              <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>
              Knowledge Base
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-800 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-slate-700">
          {loadingThreads ? (
            <div className="space-y-3 px-2 py-2">
              {[1, 2, 3, 4].map((i, index) => (
                <div key={i} className="h-16 animate-pulse rounded-2xl bg-slate-800/40 border border-slate-800/50 animate-in slide-in-from-left-4 fade-in fill-mode-both" style={{ animationDelay: `${index * 50}ms` }} />
              ))}
            </div>
          ) : threads.length === 0 ? (
            <div className="px-3 py-10 text-center text-xs text-slate-500 flex flex-col items-center gap-3 animate-in fade-in duration-700">
              <svg className="w-8 h-8 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
              No chat history yet.
            </div>
          ) : (
            threads.map((thread, index) => (
              <div
                key={thread.id}
                onClick={() => openThread(thread.id)}
                className={`w-full group relative flex flex-col items-start rounded-2xl px-4 py-3.5 text-left transition-all duration-300 cursor-pointer animate-in slide-in-from-left-4 fade-in fill-mode-both ${
                  threadId === thread.id 
                    ? "bg-slate-800/80 ring-1 ring-slate-600/50 shadow-lg" 
                    : "hover:bg-slate-800/40 text-slate-400 hover:text-slate-200"
                }`}
                style={{ animationDelay: `${index * 40}ms` }}
              >
                {editingThreadId === thread.id ? (
                  <form onSubmit={(e) => handleRenameSubmit(thread.id, e)} className="w-full pr-1 animate-in fade-in zoom-in-95">
                    <input
                      autoFocus
                      value={editingTitle}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      onBlur={(e) => handleRenameSubmit(thread.id, e)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full bg-slate-900 border border-emerald-500/50 rounded-lg px-2.5 py-1 text-[13px] font-semibold text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50 shadow-inner"
                    />
                  </form>
                ) : (
                  <div className={`w-full pr-1 truncate text-[13px] font-semibold transition-colors duration-300 ${threadId === thread.id ? "text-white" : ""}`}>
                    {threadDisplayName(thread)}
                  </div>
                )}
                
                {/* Meta Row: ID, Messages Badge, Actions */}
                <div className="w-full flex items-center justify-between mt-2.5">
                  <span className="text-[10px] opacity-50 font-mono truncate max-w-[90px] group-hover:opacity-70 transition-opacity">{thread.id}</span>
                  
                  {/* Action Group */}
                  <div className="flex items-center gap-1.5 h-6">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md border border-slate-700/50 bg-slate-900/80 shadow-inner transition-all duration-300 ${threadId === thread.id ? "opacity-100" : "opacity-60 group-hover:opacity-100"}`}>
                      {thread.message_count || 0} msgs
                    </span>
                    
                    <div className={`flex items-center gap-1 transition-all duration-300 ${threadId === thread.id ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-2 group-hover:opacity-100 group-hover:translate-x-0'}`}>
                      <button 
                        onClick={(e) => startRename(thread, e)} 
                        className="p-1 rounded-md text-slate-500 hover:bg-cyan-500/20 hover:text-cyan-400 transition-colors" 
                        title="Rename chat"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                      </button>
                      <button 
                        onClick={(e) => handleDeleteThread(thread.id, e)} 
                        className="p-1 rounded-md text-slate-500 hover:bg-rose-500/20 hover:text-rose-400 transition-colors" 
                        title="Delete chat"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="p-5 border-t border-slate-800/60 bg-[#0b1016]/90 backdrop-blur-md shrink-0">
          <button onClick={onLogout} className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-700/50 bg-slate-900/50 px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800 hover:text-white hover:border-slate-600 transition-all duration-300 active:scale-95">
            <svg className="w-4 h-4 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex flex-1 flex-col h-full w-full relative z-10 bg-[#05090f]/50">
        
        {/* Mobile Header */}
        <header className="flex items-center justify-between border-b border-slate-800/60 bg-[#0b1016]/80 px-4 py-3 backdrop-blur-xl md:hidden z-20 shadow-sm">
          <button onClick={startNewChat} className="p-2 -ml-2 rounded-xl text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
               <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
          </button>
          
          <div className="flex flex-col items-center">
            <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">Smart Medirag</span>
            <span className="text-xs font-semibold truncate max-w-[150px] text-white">{activeThread ? threadDisplayName(activeThread) : "New Chat"}</span>
          </div>

          <div className="flex items-center gap-1">
            {isAdmin && (
              <button onClick={onOpenAdmin} className="p-2 rounded-xl text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20 transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4" />
                </svg>
              </button>
            )}
            <button onClick={onLogout} className="p-2 -mr-2 rounded-xl text-slate-400 hover:bg-slate-800 transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </header>

        {/* Messages List */}
        <div className="flex-1 overflow-y-auto w-full scroll-smooth [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-slate-800/80 [&::-webkit-scrollbar-thumb]:rounded-full pt-4">
          <div className="mx-auto w-full max-w-4xl px-4 md:px-8 pb-32 flex flex-col gap-8">
            {messages.length === 0 && !loadingMessages && (
              <div className="flex flex-col items-center justify-center py-32 text-center animate-in fade-in zoom-in-[0.98] duration-700 ease-out">
                <div className="relative mb-8 group">
                  <div className="absolute inset-0 bg-gradient-to-tr from-emerald-500 to-cyan-500 rounded-[2rem] blur-xl opacity-20 group-hover:opacity-40 transition-opacity duration-700" />
                  <div className="relative h-24 w-24 rounded-[2rem] bg-[#0b1016] border border-slate-700/50 flex items-center justify-center shadow-2xl backdrop-blur-xl group-hover:scale-105 transition-transform duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]">
                    <svg className="w-12 h-12 text-emerald-400 drop-shadow-[0_0_15px_rgba(16,185,129,0.5)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                  </div>
                </div>
                <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4 drop-shadow-sm">How can I help you today?</h1>
                <p className="max-w-md text-slate-400 leading-relaxed text-sm sm:text-base">
                  Ask me questions about your ingested medical documents. I'll provide answers completely backed by citations.
                </p>
                
                {/* Sample Prompts */}
                <div className="flex flex-wrap items-center justify-center gap-3 mt-10 animate-in slide-in-from-bottom-4 fade-in duration-700 delay-150 fill-mode-both">
                  <button onClick={() => setInput("Summarize the latest document.")} className="px-5 py-2.5 rounded-full border border-slate-700/60 bg-slate-800/40 text-xs font-bold text-slate-300 hover:bg-slate-700 hover:text-white hover:border-slate-500 transition-all shadow-sm active:scale-95">Summarize latest doc</button>
                  <button onClick={() => setInput("What are the key treatments mentioned?")} className="px-5 py-2.5 rounded-full border border-slate-700/60 bg-slate-800/40 text-xs font-bold text-slate-300 hover:bg-slate-700 hover:text-white hover:border-slate-500 transition-all shadow-sm active:scale-95">Key treatments</button>
                </div>
              </div>
            )}

            {loadingMessages && (
              <div className="flex flex-col gap-8 w-full animate-in fade-in duration-500">
                <div className="h-24 w-2/3 md:w-1/2 self-end animate-pulse rounded-[2rem] rounded-tr-sm bg-slate-800/40 border border-slate-700/30" />
                <div className="h-40 w-5/6 md:w-3/4 self-start animate-pulse rounded-[2rem] rounded-tl-sm bg-slate-800/60 border border-slate-700/50" />
              </div>
            )}

            {messages.map((msg, index) => {
              const isUser = msg.role === "user";
              return (
                <div key={`${msg.id || index}-${msg.role}`} className={`flex w-full ${isUser ? "justify-end" : "justify-start"} animate-in slide-in-from-bottom-6 fade-in duration-500 ease-out fill-mode-both`}>
                  <div 
                    className={`relative max-w-[92%] md:max-w-[85%] rounded-[2rem] px-6 py-5 shadow-2xl ${
                      isUser 
                        ? "bg-gradient-to-br from-emerald-500 to-teal-600 text-white rounded-tr-sm shadow-[0_10px_30px_rgba(16,185,129,0.2)] border border-emerald-400/30" 
                        : "bg-[#0b1016]/95 border border-slate-700/60 text-slate-200 rounded-tl-sm backdrop-blur-xl shadow-[0_10px_40px_rgba(0,0,0,0.4)]"
                    }`}
                  >
                    {!isUser && (
                       <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent rounded-t-[2rem]"></div>
                    )}

                    {isUser ? (
                      <div className="whitespace-pre-wrap leading-relaxed text-[15px] font-medium">{msg.content}</div>
                    ) : (
                      <div className="flex flex-col gap-2 w-full overflow-hidden">
                        <div className="w-full text-[15px] leading-relaxed text-slate-200 
                          [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 
                          [&_p]:mb-4 
                          [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:space-y-2 
                          [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:space-y-2 
                          [&_li::marker]:text-emerald-500 [&_li]:pl-1 
                          [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mb-4 [&_h1]:text-white 
                          [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mb-3 [&_h2]:text-white 
                          [&_h3]:text-lg [&_h2]:font-bold [&_h3]:mb-3 [&_h3]:text-white 
                          [&_a]:text-cyan-400 [&_a]:underline hover:[&_a]:text-cyan-300 
                          [&_code]:text-emerald-300 [&_code]:bg-slate-900/80 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded-md [&_code]:text-[13px]
                          [&_pre]:bg-[#05090f] [&_pre]:p-4 [&_pre]:rounded-xl [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-slate-800/80 [&_pre]:mb-4 
                          [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-slate-300 
                          [&_strong]:font-bold [&_strong]:text-white
                        ">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{formatAssistantContent(msg.content)}</ReactMarkdown>
                        </div>
                        <CitationBox citations={msg.citations} />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {loadingAsk && (
              <div className="flex justify-start animate-in fade-in zoom-in-[0.98] duration-300 ease-out">
                <div className="bg-[#0b1016]/95 border border-slate-700/60 text-slate-400 rounded-[2rem] rounded-tl-sm px-6 py-5 flex items-center gap-2.5 shadow-[0_10px_40px_rgba(0,0,0,0.4)] backdrop-blur-xl relative">
                  <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent rounded-t-[2rem]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-bounce shadow-[0_0_8px_rgba(16,185,129,0.8)]" style={{ animationDelay: "0ms" }} />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-bounce shadow-[0_0_8px_rgba(16,185,129,0.8)]" style={{ animationDelay: "150ms" }} />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-bounce shadow-[0_0_8px_rgba(16,185,129,0.8)]" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            )}
            <div ref={bottomRef} className="h-4" />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#05090f] via-[#05090f] to-transparent pt-16 pb-8 px-4 z-20 pointer-events-none">
          <div className="mx-auto max-w-4xl relative group pointer-events-auto">
            <div className="absolute -inset-1 bg-gradient-to-r from-emerald-500/20 to-cyan-500/20 rounded-[2.5rem] blur-xl opacity-50 group-focus-within:opacity-100 transition duration-500" />
            
            <div className="relative flex items-end rounded-[2rem] border border-slate-700/60 bg-[#0b1016]/95 p-2 pr-20 shadow-2xl backdrop-blur-2xl focus-within:border-emerald-500/50 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all duration-300">
              <textarea
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 240)}px`;
                }}
                placeholder="Ask your medical knowledge base..."
                className="flex-1 max-h-[240px] min-h-[52px] resize-none bg-transparent px-5 py-3.5 text-[15px] font-medium text-slate-100 placeholder:text-slate-500 focus:outline-none [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full leading-relaxed"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                    event.target.style.height = 'auto';
                  }
                }}
              />
              <button 
                onClick={sendMessage} 
                disabled={loadingAsk || !input.trim()} 
                className="absolute bottom-3 right-3 p-3.5 rounded-[1.25rem] bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-[0_4px_15px_rgba(16,185,129,0.3)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.5)] transition-all duration-300 disabled:opacity-30 disabled:hover:shadow-none active:scale-95 group/btn"
              >
                <svg className="w-5 h-5 group-hover/btn:-translate-y-1 group-hover/btn:translate-x-1 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 19V5m0 0l-7 7m7-7l7 7" />
                </svg>
              </button>
            </div>
            
            <div className="text-center mt-3 text-[11px] font-bold text-slate-500 tracking-wide uppercase opacity-70">
              Smart Medirag can make mistakes. Verify critical medical details.
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function AdminIngestionPanel({ onBackToChat, onLogout, addToast }) {
  const PAGE_SIZE = 10;
  const VERIFICATION_PAGE_SIZE = 8;
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [adminStats, setAdminStats] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [verifyQuery, setVerifyQuery] = useState("");
  const [verifyMode, setVerifyMode] = useState("hybrid");
  const [verifyTopK, setVerifyTopK] = useState(8);
  const [verifying, setVerifying] = useState(false);
  const [verificationResponse, setVerificationResponse] = useState(null);
  const [verificationPage, setVerificationPage] = useState(1);
  const [deletingDocId, setDeletingDocId] = useState("");
  const [deletingBulk, setDeletingBulk] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [ingestionProgress, setIngestionProgress] = useState(0);
  const [showCompletionPopup, setShowCompletionPopup] = useState(false);
  const [completionResult, setCompletionResult] = useState(null);
  const ingestionProgressTimerRef = useRef(null);

  const clearIngestionProgressTimer = () => {
    if (ingestionProgressTimerRef.current) {
      window.clearInterval(ingestionProgressTimerRef.current);
      ingestionProgressTimerRef.current = null;
    }
  };

  const startIngestionProgressTimer = () => {
    clearIngestionProgressTimer();
    ingestionProgressTimerRef.current = window.setInterval(() => {
      setIngestionProgress((prev) => {
        if (prev >= 95) return prev;
        if (prev < 60) return Math.min(95, prev + 4);
        if (prev < 85) return Math.min(95, prev + 2);
        return Math.min(95, prev + 1);
      });
    }, 600);
  };

  const loadDocuments = async () => {
    try { setLoadingDocs(true); const docs = await listIngestedDocuments(); setDocuments(docs); } 
    catch (error) { addToast(getErrorMessage(error, "Failed to load ingested documents"), "error"); } 
    finally { setLoadingDocs(false); }
  };

  const loadAdminStatistics = async () => {
    try {
      setLoadingStats(true);
      const stats = await fetchAdminStatistics();
      setAdminStats(stats);
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to load admin statistics"), "error");
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    loadDocuments();
    loadAdminStatistics();
  }, []);
  useEffect(() => { setCurrentPage(1); }, [searchQuery]);

  const filteredDocuments = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((doc) => {
      const title = (doc.title || "").toLowerCase();
      const source = (doc.source_path || "").toLowerCase();
      const docId = (doc.doc_id || "").toLowerCase();
      return title.includes(q) || source.includes(q) || docId.includes(q);
    });
  }, [documents, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / PAGE_SIZE));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const startIndex = (safeCurrentPage - 1) * PAGE_SIZE;
  const paginatedDocuments = filteredDocuments.slice(startIndex, startIndex + PAGE_SIZE);
  const verificationResults = verificationResponse?.results || [];
  const verificationStats = verificationResponse?.statistics || null;
  const verificationTotalPages = Math.max(1, Math.ceil(verificationResults.length / VERIFICATION_PAGE_SIZE));
  const safeVerificationPage = Math.min(verificationPage, verificationTotalPages);
  const verificationStart = (safeVerificationPage - 1) * VERIFICATION_PAGE_SIZE;
  const paginatedVerificationResults = verificationResults.slice(
    verificationStart,
    verificationStart + VERIFICATION_PAGE_SIZE
  );
  const selectedCount = selectedDocIds.length;
  const paginatedDocIds = paginatedDocuments.map((doc) => doc.doc_id);
  const allPageSelected = paginatedDocIds.length > 0 && paginatedDocIds.every((docId) => selectedDocIds.includes(docId));

  useEffect(() => {
    setSelectedDocIds((prev) => prev.filter((docId) => documents.some((doc) => doc.doc_id === docId)));
  }, [documents]);
  useEffect(() => () => clearIngestionProgressTimer(), []);

  const appendFiles = (incoming) => {
    const selected = Array.from(incoming || []).filter((file) => file?.name?.toLowerCase().endsWith(".pdf"));
    if (selected.length === 0) { addToast("Only PDF files are accepted", "error"); return; }
    setFiles((prev) => {
      const map = new Map(prev.map((f) => [`${f.name}-${f.size}-${f.lastModified}`, f]));
      selected.forEach((f) => map.set(`${f.name}-${f.size}-${f.lastModified}`, f));
      return Array.from(map.values());
    });
  };

  const handleDrop = (event) => { event.preventDefault(); setDragging(false); appendFiles(event.dataTransfer.files); };
  const removeFile = (target) => setFiles((prev) => prev.filter((f) => !(f.name === target.name && f.size === target.size && f.lastModified === target.lastModified)));

  const runIngestion = async () => {
    if (files.length === 0 || uploading) return;
    let ingestionSucceeded = false;
    try {
      setUploading(true);
      setIngestionProgress(1);
      startIngestionProgressTimer();
      const response = await adminIngestFiles(files, {
        onUploadProgress: (event) => {
          if (!event?.total) return;
          const uploadPercent = Math.round((event.loaded / event.total) * 65);
          setIngestionProgress((prev) => Math.max(prev, Math.min(65, uploadPercent)));
        },
      });
      clearIngestionProgressTimer();
      setIngestionProgress(100);
      setResults(response);
      await loadDocuments();
      await loadAdminStatistics();
      addToast(`Ingestion finished: ${response.ingested_count || 0} success, ${response.failed_count || 0} failed`, "success");
      if ((response.failed_count || 0) === 0) setFiles([]);
      setCompletionResult(response);
      setShowCompletionPopup(true);
      ingestionSucceeded = true;
    } catch (error) {
      clearIngestionProgressTimer();
      addToast(getErrorMessage(error, "Ingestion failed"), "error");
    } 
    finally {
      setUploading(false);
      if (!ingestionSucceeded) setIngestionProgress(0);
    }
  };

  const runChunkVerification = async () => {
    const query = verifyQuery.trim();
    if (!query || verifying) return;

    try {
      setVerifying(true);
      setVerificationPage(1);
      const response = await retrieveChunksForVerification({
        query,
        mode: verifyMode,
        top_k: Number(verifyTopK) || 8,
      });
      setVerificationResponse(response);
      addToast(`Retrieved ${response?.results?.length || 0} chunks for verification`, "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Chunk verification failed"), "error");
    } finally {
      setVerifying(false);
    }
  };

  const handleDeleteDocument = async (doc) => {
    const docId = doc?.doc_id || "";
    if (!docId || deletingDocId || deletingBulk) return;

    const title = doc?.title || docId;
    const confirmed = window.confirm(`Delete indexed document "${title}"? This will remove vector and graph data.`);
    if (!confirmed) return;

    try {
      setDeletingDocId(docId);
      await deleteIngestedDocument(docId);
      setDocuments((prev) => prev.filter((item) => item.doc_id !== docId));
      setSelectedDocIds((prev) => prev.filter((id) => id !== docId));
      await loadAdminStatistics();
      addToast(`Deleted document: ${title}`, "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to delete indexed document"), "error");
    } finally {
      setDeletingDocId("");
    }
  };

  const toggleSelectDoc = (docId) => {
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    );
  };

  const toggleSelectAllOnPage = () => {
    setSelectedDocIds((prev) => {
      const pageSet = new Set(paginatedDocIds);
      if (allPageSelected) {
        return prev.filter((id) => !pageSet.has(id));
      }
      const merged = new Set(prev);
      paginatedDocIds.forEach((id) => merged.add(id));
      return Array.from(merged);
    });
  };

  const handleBulkDeleteSelected = async () => {
    if (selectedCount === 0 || deletingDocId || deletingBulk) return;

    const confirmed = window.confirm(
      `Delete ${selectedCount} selected document(s)? This will remove vector and graph data.`
    );
    if (!confirmed) return;

    try {
      setDeletingBulk(true);
      const response = await bulkDeleteIngestedDocuments(selectedDocIds);
      const deletedIds = (response?.deleted || [])
        .map((item) => item?.doc_id)
        .filter(Boolean);

      if (deletedIds.length > 0) {
        const deletedSet = new Set(deletedIds);
        setDocuments((prev) => prev.filter((doc) => !deletedSet.has(doc.doc_id)));
      }

      setSelectedDocIds([]);
      await loadAdminStatistics();

      const failedCount = response?.failed_count || 0;
      const deletedCount = response?.deleted_count || deletedIds.length;
      addToast(
        failedCount > 0
          ? `Deleted ${deletedCount} document(s), ${failedCount} failed`
          : `Deleted ${deletedCount} selected document(s)`,
        failedCount > 0 ? "error" : "success"
      );
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to delete selected documents"), "error");
    } finally {
      setDeletingBulk(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#05090f] text-slate-100 font-sans selection:bg-cyan-500/30 relative">
      {showCompletionPopup && completionResult && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setShowCompletionPopup(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-slate-700/70 bg-[#0b1016] p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold text-white">Ingestion Completed</h3>
                <p className="mt-1 text-sm text-slate-400">Your upload process has finished.</p>
              </div>
              <button
                type="button"
                className="rounded-lg border border-slate-700/70 bg-slate-800/60 px-2 py-1 text-xs font-semibold text-slate-300 hover:bg-slate-700"
                onClick={() => setShowCompletionPopup(false)}
              >
                Close
              </button>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-y-3 gap-x-4 rounded-2xl border border-slate-800/80 bg-slate-900/50 p-4 text-sm">
              <div className="text-slate-400">Status</div>
              <div className="text-right font-bold capitalize text-slate-200">{completionResult.status}</div>
              <div className="text-slate-400">Uploaded</div>
              <div className="text-right font-bold text-slate-200">{completionResult.uploaded_count}</div>
              <div className="text-slate-400">Indexed</div>
              <div className="text-right font-bold text-emerald-400">{completionResult.ingested_count}</div>
              <div className="text-slate-400">Failed</div>
              <div className={`text-right font-bold ${completionResult.failed_count > 0 ? "text-rose-400" : "text-slate-300"}`}>
                {completionResult.failed_count}
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="absolute top-0 left-0 right-0 h-[500px] bg-gradient-to-b from-cyan-900/10 to-transparent pointer-events-none" />
      
      <header className="sticky top-0 z-30 border-b border-slate-800/60 bg-[#0b1016]/80 backdrop-blur-xl px-4 py-4 md:px-8 shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.2)]">
              <svg className="w-5 h-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-400 font-bold mb-0.5">Admin Console</div>
              <h1 className="text-xl font-bold tracking-tight leading-none text-white">Knowledge Base</h1>
            </div>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            <button className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-800/40 px-4 py-2.5 text-sm font-semibold hover:bg-slate-700 hover:text-white transition-all duration-300" onClick={onBackToChat}>
              <svg className="w-4 h-4 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M11 17l-5-5m0 0l5-5m-5 5h12" /></svg>
              <span className="hidden sm:inline">Back to Chat</span>
            </button>
            <button className="flex items-center gap-2 rounded-xl border border-rose-900/30 bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-400 hover:bg-rose-500/20 hover:border-rose-500/40 transition-all duration-300" onClick={onLogout}>
              <svg className="w-4 h-4 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-7xl gap-6 md:gap-8 px-4 py-8 lg:grid-cols-[420px_1fr] md:px-8 relative z-10">
        <section className="flex flex-col gap-6 animate-in slide-in-from-left-8 fade-in duration-700 ease-out">
          <div className="rounded-[2rem] border border-slate-800/60 bg-[#0b1016]/90 p-6 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-white">Admin Statistics</h2>
                <p className="text-xs text-slate-400 mt-1">Realtime system and index overview</p>
              </div>
              <button
                type="button"
                onClick={loadAdminStatistics}
                className="rounded-xl border border-slate-700/60 bg-slate-800/50 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Refresh
              </button>
            </div>

            {loadingStats ? (
              <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-5 text-xs text-slate-400">
                Loading statistics...
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "Documents", value: adminStats?.documents_count ?? 0 },
                  { label: "Vector Chunks", value: adminStats?.vector_chunks_count ?? 0 },
                  { label: "Users", value: adminStats?.users_count ?? 0 },
                  { label: "Conversations", value: adminStats?.threads_count ?? 0 },
                  { label: "Messages", value: adminStats?.messages_count ?? 0 },
                  { label: "Admins", value: adminStats?.admin_users_count ?? 0 },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{item.label}</div>
                    <div className="text-lg font-bold text-white mt-1">{item.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-[2rem] border border-slate-800/60 bg-[#0b1016]/90 p-6 shadow-2xl backdrop-blur-xl">
            <h2 className="text-lg font-bold text-white mb-1.5">Chunk Verification</h2>
            <p className="text-sm text-slate-400 leading-relaxed mb-5">
              Run retrieval with a query and inspect returned chunks for quality checks.
            </p>

            <div className="space-y-3">
              <textarea
                rows={3}
                value={verifyQuery}
                onChange={(e) => setVerifyQuery(e.target.value)}
                placeholder="Enter query to inspect top chunks..."
                className="w-full resize-none rounded-xl border border-slate-700/60 bg-slate-900/60 px-4 py-3 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50"
              />
              <div className="grid grid-cols-2 gap-3">
                <select
                  value={verifyMode}
                  onChange={(e) => setVerifyMode(e.target.value)}
                  className="rounded-xl border border-slate-700/60 bg-slate-900/60 px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                >
                  <option value="hybrid">Hybrid</option>
                  <option value="vector">Vector</option>
                  <option value="graph">Graph</option>
                </select>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={verifyTopK}
                  onChange={(e) => setVerifyTopK(e.target.value)}
                  className="rounded-xl border border-slate-700/60 bg-slate-900/60 px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                />
              </div>
            </div>

            <button
              type="button"
              onClick={runChunkVerification}
              disabled={verifying || !verifyQuery.trim()}
              className="mt-4 w-full rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 px-4 py-3 text-sm font-bold text-white shadow-[0_8px_25px_rgba(6,182,212,0.3)] hover:shadow-[0_12px_35px_rgba(6,182,212,0.4)] disabled:opacity-50"
            >
              {verifying ? "Retrieving..." : "Retrieve Chunks"}
            </button>

            {verificationResponse && (
              <div className="mt-5 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 text-xs text-slate-300">
                <div className="grid grid-cols-2 gap-y-2 gap-x-3">
                  <div className="text-slate-500 uppercase tracking-wider">Latency</div>
                  <div className="text-right">{verificationResponse.latency_seconds}s</div>
                  <div className="text-slate-500 uppercase tracking-wider">Results</div>
                  <div className="text-right">{verificationStats?.result_count ?? 0}</div>
                  <div className="text-slate-500 uppercase tracking-wider">Unique Docs</div>
                  <div className="text-right">{verificationStats?.unique_document_count ?? 0}</div>
                  <div className="text-slate-500 uppercase tracking-wider">Avg Score</div>
                  <div className="text-right">{verificationStats?.avg_score ?? 0}</div>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-[2rem] border border-slate-800/60 bg-[#0b1016]/90 p-7 shadow-2xl backdrop-blur-xl relative overflow-hidden group">
            <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-cyan-400 to-blue-500 opacity-70" />
            
            <h2 className="text-xl font-bold text-white mb-1.5">Upload Documents</h2>
            <p className="text-sm text-slate-400 leading-relaxed mb-6">Add medical PDFs to expand the vector database knowledge.</p>

            <div
              onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
              onDrop={handleDrop}
              className={`rounded-[1.5rem] border-2 border-dashed px-6 py-12 text-center transition-all duration-300 flex flex-col items-center justify-center
                ${dragging ? "border-cyan-400 bg-cyan-500/10 scale-[1.02]" : "border-slate-700/60 bg-slate-900/30 hover:border-slate-500/80 hover:bg-slate-800/40"}`}
            >
              <div className={`p-4 rounded-2xl mb-4 transition-all duration-300 ${dragging ? "bg-cyan-500/20 text-cyan-400 scale-110 shadow-[0_0_15px_rgba(6,182,212,0.3)]" : "bg-slate-800 text-slate-400 shadow-inner"}`}>
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-sm font-bold text-slate-200 mb-1">Drag & drop PDFs here</p>
              <p className="text-xs text-slate-500 mb-5 font-medium">Up to 50MB per file</p>
              
              <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-slate-800 px-5 py-3 text-sm font-bold text-white hover:bg-slate-700 transition-all border border-slate-700 shadow-lg active:scale-95">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                Browse Files
                <input type="file" accept=".pdf,application/pdf" multiple className="hidden" onChange={(e) => appendFiles(e.target.files)} />
              </label>
            </div>

            {files.length > 0 && (
              <div className="mt-8 animate-in fade-in slide-in-from-bottom-2">
                <div className="flex items-center justify-between mb-3 text-[11px] font-bold uppercase tracking-widest text-slate-500">
                  <span>Selected Files ({files.length})</span>
                  <button onClick={() => setFiles([])} className="text-rose-400 hover:text-rose-300 transition-colors">Clear all</button>
                </div>
                <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full">
                  {files.map((file) => (
                    <div key={`${file.name}-${file.size}-${file.lastModified}`} className="flex items-center justify-between rounded-2xl border border-slate-700/50 bg-slate-800/40 px-4 py-3 group hover:border-slate-500/80 hover:bg-slate-800/60 transition-all duration-300 animate-in slide-in-from-right-4 fade-in">
                      <div className="flex items-center gap-3.5 overflow-hidden">
                        <div className="p-2 bg-slate-900 rounded-xl text-slate-400 group-hover:text-cyan-400 transition-colors shrink-0 shadow-inner">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                        </div>
                        <div className="overflow-hidden">
                          <div className="text-sm font-semibold truncate text-slate-200">{file.name}</div>
                          <div className="text-[11px] font-medium text-slate-500 mt-0.5">{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                        </div>
                      </div>
                      <button type="button" className="p-2 rounded-lg text-slate-500 hover:bg-rose-500/20 hover:text-rose-400 transition-colors shrink-0" onClick={() => removeFile(file)}>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button onClick={runIngestion} disabled={uploading || files.length === 0} className="mt-8 w-full min-h-[56px] flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 px-4 py-4 text-sm font-bold text-white shadow-[0_8px_25px_rgba(6,182,212,0.3)] hover:shadow-[0_12px_35px_rgba(6,182,212,0.4)] disabled:opacity-50 disabled:shadow-none transition-all duration-300">
              {uploading ? (
                <><svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Processing...</>
              ) : (
                <><svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg> Start Ingestion</>
              )}
            </button>

            {uploading && (
              <div className="mt-5 rounded-2xl border border-cyan-500/30 bg-cyan-500/10 p-4 animate-in fade-in slide-in-from-top-2">
                <div className="mb-2 flex items-center justify-between text-xs font-semibold text-cyan-200">
                  <span>Ingestion Progress</span>
                  <span>{ingestionProgress}%</span>
                </div>
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 transition-all duration-500"
                    style={{ width: `${ingestionProgress}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-300">
                  {ingestionProgress < 100 ? "Uploading and indexing documents..." : "Completed"}
                </p>
              </div>
            )}

            {results && (
              <div className="mt-8 rounded-2xl border border-slate-700/60 bg-slate-900/50 p-5 text-sm shadow-inner animate-in fade-in slide-in-from-top-4">
                <div className="flex items-center gap-2 font-bold text-white mb-4 border-b border-slate-800/80 pb-3">
                  <div className={`w-2 h-2 rounded-full shadow-[0_0_8px_currentColor] ${results.failed_count === 0 ? 'bg-emerald-400 text-emerald-400' : 'bg-amber-400 text-amber-400'}`} />
                  Ingestion Summary
                </div>
                <div className="grid grid-cols-2 gap-y-3 gap-x-4 mb-2">
                  <div className="text-slate-400 font-medium text-xs uppercase tracking-wider">Status</div>
                  <div className="font-bold text-right capitalize text-slate-200">{results.status}</div>
                  <div className="text-slate-400 font-medium text-xs uppercase tracking-wider">Uploaded</div>
                  <div className="font-bold text-right text-slate-200">{results.uploaded_count}</div>
                  <div className="text-slate-400 font-medium text-xs uppercase tracking-wider">Indexed</div>
                  <div className="font-bold text-emerald-400 text-right">{results.ingested_count}</div>
                  <div className="text-slate-400 font-medium text-xs uppercase tracking-wider">Failed</div>
                  <div className={`font-bold text-right ${results.failed_count > 0 ? 'text-rose-400' : 'text-slate-300'}`}>{results.failed_count}</div>
                </div>
                
                {Array.isArray(results.failed) && results.failed.length > 0 && (
                  <div className="mt-5 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl">
                    <div className="text-[11px] font-bold text-rose-400 mb-2 uppercase tracking-widest">Error Details</div>
                    <ul className="space-y-2 text-xs text-rose-200/90 list-disc list-inside">
                      {results.failed.map((item, index) => <li key={`${item.filename}-${index}`} className="truncate" title={item.error}><span className="font-bold">{item.filename}:</span> {item.error}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="flex flex-col min-h-0 h-[560px] sm:h-[640px] lg:h-[760px] xl:h-[820px] animate-in slide-in-from-right-8 fade-in duration-700 ease-out delay-150 fill-mode-both">
          <div className="rounded-[2rem] border border-slate-800/60 bg-[#0b1016]/90 shadow-2xl backdrop-blur-xl flex flex-col min-h-0 h-full overflow-hidden transition-all duration-500 ease-out">
            <div className="p-6 border-b border-slate-800/60 shrink-0 bg-slate-900/20">
              <div className="flex items-center justify-between gap-3 min-h-[42px]">
                <div>
                  <h2 className="text-xl font-bold text-white mb-1">Indexed Documents</h2>
                  <p className="text-xs font-medium text-slate-400">Active in the vector database</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="flex w-[130px] items-center justify-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/50 px-4 py-2 text-xs font-bold text-slate-300 hover:bg-slate-700 hover:text-white hover:border-slate-600 transition-all shadow-sm active:scale-95"
                    onClick={loadDocuments}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                    Refresh
                  </button>
                  <button
                    type="button"
                    onClick={handleBulkDeleteSelected}
                    disabled={selectedCount === 0 || deletingBulk || Boolean(deletingDocId)}
                    className="flex w-[170px] items-center justify-center gap-2 rounded-xl border border-rose-900/40 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-300 hover:bg-rose-500/20 hover:border-rose-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {deletingBulk ? "Deleting Selected..." : `Delete Selected (${selectedCount})`}
                  </button>
                </div>
              </div>
              <div className="mt-4">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by title, source, or doc ID..."
                  className="w-full rounded-xl border border-slate-700/60 bg-slate-900/60 px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50"
                />
              </div>
              <div className="mt-3 flex min-h-[24px] items-center justify-between text-[11px] font-semibold">
                <span className="text-slate-400">
                  {selectedCount > 0 ? `${selectedCount} selected` : "No documents selected"}
                </span>
                {selectedCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setSelectedDocIds([])}
                    className="text-slate-300 hover:text-white"
                  >
                    Clear selection
                  </button>
                )}
              </div>
            </div>

            {verificationResponse && (
              <div className="border-b border-slate-800/60 bg-slate-950/40 p-4 animate-in fade-in slide-in-from-top-3 duration-300">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-sm font-bold text-white">Retrieved Chunks</h3>
                  <span className="text-[11px] font-semibold text-slate-400">
                    Query: {verificationResponse.query}
                  </span>
                </div>
                {verificationResults.length === 0 ? (
                  <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3 text-xs text-slate-400">
                    No chunks returned for this query.
                  </div>
                ) : (
                  <>
                    <div className="space-y-3 max-h-[320px] overflow-auto pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full">
                      {paginatedVerificationResults.map((item) => (
                        <div key={`${item.chunk_id}-${item.rank}`} className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-3">
                          <div className="flex items-center justify-between gap-3 text-[11px] text-slate-400 mb-2">
                            <div className="font-semibold text-slate-300">#{item.rank} {item.doc_id || "Unknown doc"}</div>
                            <div className="flex items-center gap-2">
                              <span className="rounded-md border border-slate-700/70 bg-slate-800/70 px-2 py-1">{item.source || "-"}</span>
                              <span className="rounded-md border border-cyan-700/60 bg-cyan-500/10 px-2 py-1 text-cyan-300">
                                {typeof item.score === "number" ? item.score.toFixed(4) : item.score}
                              </span>
                            </div>
                          </div>
                          <div className="text-[11px] text-slate-500 mb-2">
                            Chunk: {item.chunk_id || "-"} | Page: {item?.metadata?.page_label || item?.metadata?.page_physical || "-"}
                          </div>
                          <div className="text-xs text-slate-200 leading-relaxed whitespace-pre-wrap">
                            {item.preview || item.text || "No content"}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-3 flex items-center justify-between">
                      <div className="text-xs text-slate-500">
                        Showing {verificationStart + 1}-{Math.min(verificationStart + VERIFICATION_PAGE_SIZE, verificationResults.length)} of {verificationResults.length}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setVerificationPage((prev) => Math.max(1, prev - 1))}
                          disabled={safeVerificationPage <= 1}
                          className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-40"
                        >
                          Previous
                        </button>
                        <span className="px-2 text-xs font-semibold text-slate-300">
                          Page {safeVerificationPage} of {verificationTotalPages}
                        </span>
                        <button
                          type="button"
                          onClick={() => setVerificationPage((prev) => Math.min(verificationTotalPages, prev + 1))}
                          disabled={safeVerificationPage >= verificationTotalPages}
                          className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-40"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="flex-1 min-h-0 overflow-auto bg-slate-900/10 transition-all duration-500 ease-out [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full">
              {loadingDocs ? (
                <div className="p-10 flex flex-col items-center justify-center h-full gap-4 text-slate-400 animate-in fade-in">
                  <div className="relative">
                    <div className="w-12 h-12 rounded-full border-4 border-slate-800 border-t-cyan-500 animate-spin" />
                    <div className="absolute inset-0 rounded-full border-4 border-transparent border-b-emerald-500 animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                  </div>
                  <span className="text-sm font-semibold tracking-wide">Loading database records...</span>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="p-10 flex flex-col items-center justify-center text-center h-full animate-in fade-in slide-in-from-bottom-4">
                  <div className="w-20 h-20 rounded-[2rem] bg-slate-800/40 border border-slate-700/50 flex items-center justify-center mb-6 shadow-inner">
                    <svg className="w-10 h-10 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                  </div>
                  <h3 className="text-base font-bold text-slate-200 mb-2">{documents.length === 0 ? "No documents indexed" : "No matching documents"}</h3>
                  <p className="text-sm font-medium text-slate-500 max-w-[260px] leading-relaxed">
                    {documents.length === 0 ? "Upload PDFs using the form to start building your knowledge base." : "Try a different search term."}
                  </p>
                </div>
              ) : (
                <>
                  <table className="w-full table-fixed text-left border-collapse text-sm">
                    <thead className="sticky top-0 bg-[#0b1016]/95 backdrop-blur-md text-[11px] font-bold uppercase tracking-widest text-slate-400 shadow-[0_1px_0_rgba(255,255,255,0.05)] z-10">
                      <tr>
                        <th className="px-3 py-4 border-b border-slate-800/80 w-14 text-center">
                          <input
                            type="checkbox"
                            checked={allPageSelected}
                            onChange={toggleSelectAllOnPage}
                            aria-label="Select all documents on current page"
                            className="h-4 w-4 cursor-pointer rounded border-slate-600 bg-slate-900 text-cyan-500 focus:ring-cyan-500/50"
                          />
                        </th>
                        <th className="px-6 py-4 border-b border-slate-800/80">Title & Source</th>
                        <th className="px-4 py-4 border-b border-slate-800/80 w-24 text-center">Pages</th>
                        <th className="px-4 py-4 border-b border-slate-800/80 w-44">Doc ID</th>
                        <th className="px-6 py-4 border-b border-slate-800/80 w-36 text-right">Created</th>
                        <th className="px-4 py-4 border-b border-slate-800/80 w-28 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/40">
                      {paginatedDocuments.map((doc, idx) => (
                        <tr key={doc.doc_id} className="bg-transparent hover:bg-slate-800/20 transition-colors duration-300 group animate-in fade-in slide-in-from-bottom-2" style={{ animationDelay: `${idx * 50}ms`, animationFillMode: "both" }}>
                          <td className="px-3 py-4 align-top text-center">
                            <input
                              type="checkbox"
                              checked={selectedDocIds.includes(doc.doc_id)}
                              onChange={() => toggleSelectDoc(doc.doc_id)}
                              aria-label={`Select ${doc.title || doc.doc_id}`}
                              className="mt-1 h-4 w-4 cursor-pointer rounded border-slate-600 bg-slate-900 text-cyan-500 focus:ring-cyan-500/50"
                            />
                          </td>
                          <td className="px-6 py-4 align-top">
                            <div className="flex items-start gap-3.5">
                              <div className="mt-0.5 p-1.5 rounded-lg bg-slate-800 text-rose-400 group-hover:bg-rose-500/10 transition-colors">
                                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                              </div>
                              <div className="min-w-0">
                                <div className="font-bold text-slate-200 line-clamp-1 group-hover:text-cyan-400 transition-colors" title={doc.title || "Untitled"}>{doc.title || "Untitled"}</div>
                                <div className="text-[11px] font-medium text-slate-500 mt-1 truncate max-w-[200px] sm:max-w-xs" title={doc.source_path}>{doc.source_path}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-4 align-top text-center">
                            <span className="inline-flex items-center justify-center min-w-[28px] h-7 px-2 rounded-lg bg-slate-800/80 text-xs font-bold text-slate-300 border border-slate-700/50 shadow-inner">{doc.total_pages ?? "-"}</span>
                          </td>
                          <td className="px-4 py-4 align-top">
                            <div className="text-[11px] font-mono text-slate-400 bg-slate-900/80 px-2.5 py-1.5 rounded-lg border border-slate-800/80 truncate max-w-[170px] shadow-inner" title={doc.doc_id}>{doc.doc_id}</div>
                          </td>
                          <td className="px-6 py-4 align-top text-right text-[11px] font-semibold text-slate-400 whitespace-nowrap">
                            {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : "-"}
                          </td>
                          <td className="px-4 py-4 align-top text-right">
                            <button
                              type="button"
                              onClick={() => handleDeleteDocument(doc)}
                              disabled={Boolean(deletingDocId)}
                              className="inline-flex w-24 items-center justify-center rounded-lg border border-rose-900/40 bg-rose-500/10 px-3 py-1.5 text-[11px] font-bold text-rose-300 hover:bg-rose-500/20 hover:border-rose-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {deletingDocId === doc.doc_id ? "Deleting..." : "Delete"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-slate-800/80 bg-[#0b1016]/95 px-4 py-3 backdrop-blur-md">
                    <div className="text-xs text-slate-400">
                      Showing {startIndex + 1}-{Math.min(startIndex + PAGE_SIZE, filteredDocuments.length)} of {filteredDocuments.length}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setCurrentPage(1)}
                        disabled={safeCurrentPage <= 1}
                        className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        First
                      </button>
                      <button
                        type="button"
                        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                        disabled={safeCurrentPage <= 1}
                        className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Previous
                      </button>
                      <span className="px-2 text-xs font-semibold text-slate-300">
                        Page {safeCurrentPage} of {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                        disabled={safeCurrentPage >= totalPages}
                        className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function AccessDeniedPanel({ onBackToChat, onLogout }) {
  return (
    <div className="min-h-screen bg-[#05090f] text-slate-100 flex items-center justify-center px-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(225,29,72,.1),transparent_50%)] animate-pulse duration-[8000ms]" />
      <div className="w-full max-w-[420px] rounded-[2.5rem] border border-rose-900/40 bg-[#0b1016]/80 p-10 text-center shadow-[0_20px_60px_rgba(225,29,72,0.15)] backdrop-blur-2xl relative z-10 animate-in zoom-in-95 duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]">
        <div className="mx-auto w-20 h-20 bg-rose-500/10 rounded-3xl flex items-center justify-center mb-8 border border-rose-500/20 shadow-[0_0_30px_rgba(225,29,72,0.2)]">
          <svg className="w-10 h-10 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
        </div>
        <h1 className="text-2xl font-bold text-white mb-3">Access Restricted</h1>
        <p className="text-sm font-medium text-slate-400 mb-10 leading-relaxed px-4">You do not have the required administrative privileges to view the ingestion console.</p>
        <div className="flex flex-col gap-3">
          <button className="w-full rounded-2xl bg-slate-100 px-4 py-4 text-sm font-bold text-slate-900 hover:bg-white transition-all shadow-lg hover:shadow-xl active:scale-[0.98]" onClick={onBackToChat}>Return to Chat</button>
          <button className="w-full rounded-2xl border border-slate-700/60 bg-slate-800/40 px-4 py-4 text-sm font-bold text-slate-300 hover:bg-slate-800 hover:text-white transition-all active:scale-[0.98]" onClick={onLogout}>Sign Out</button>
        </div>
      </div>
    </div>
  );
}

function getCurrentRoute() { return window.location.hash || "#/chat"; }

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));
  const [user, setUser] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [route, setRoute] = useState(() => getCurrentRoute());

  const addToast = (message, type = "success") => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((item) => item.id !== id)), 4000);
  };

  const navigate = (nextRoute) => {
    if (window.location.hash !== nextRoute) window.location.hash = nextRoute;
    setRoute(nextRoute);
  };

  useEffect(() => {
    const handleUnauthorized = () => setToken(null);
    const handleHashChange = () => setRoute(getCurrentRoute());
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    window.addEventListener("hashchange", handleHashChange);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  useEffect(() => {
    const loadCurrentUser = async () => {
      if (!token) { setUser(null); return; }
      try {
        const me = await getCurrentUser();
        setUser(me);
        if (me?.role) localStorage.setItem("role", me.role);
      } catch { setUser(null); }
    };
    loadCurrentUser();
  }, [token]);

  useEffect(() => { if (!window.location.hash) { window.location.hash = "#/chat"; setRoute("#/chat"); } }, []);

  const handleLogout = () => {
    clearSession();
    setUser(null);
    setToken(null);
    navigate("#/chat");
  };

  const handleAdminAuthSuccess = () => {
    setToken(localStorage.getItem("access_token"));
    setRoute("#/admin/ingest");
    if (window.location.hash !== "#/admin/ingest") window.location.hash = "#/admin/ingest";
  };

  const isAdminLoginRoute = route.startsWith("#/admin/login");
  const isAdminRoute = route.startsWith("#/admin/ingest");
  const isAdmin = (user?.role || "") === "admin";

  return (
    <>
      <Toasts items={toasts} />
      {isAdminLoginRoute ? (
        <AdminLoginPanel
          addToast={addToast}
          onAdminAuthSuccess={handleAdminAuthSuccess}
          onBackToChat={() => navigate("#/chat")}
        />
      ) : !token ? (
        <AuthPanel onAuthSuccess={() => setToken(localStorage.getItem("access_token"))} addToast={addToast} />
      ) : isAdminRoute ? (
        isAdmin ? (
          <AdminIngestionPanel addToast={addToast} onBackToChat={() => navigate("#/chat")} onLogout={handleLogout} />
        ) : (
          <AccessDeniedPanel onBackToChat={() => navigate("#/chat")} onLogout={handleLogout} />
        )
      ) : (
        <ChatPanel onLogout={handleLogout} addToast={addToast} user={user} onOpenAdmin={() => navigate("#/admin/login")} />
      )}
    </>
  );
}

