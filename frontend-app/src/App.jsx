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
import { askQuestion, deleteThread, listThreadMessages, listThreads } from "./api/answer";


function getErrorMessage(error, fallback) {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  return error.message || error.error || fallback;
}


function Toasts({ items }) {
  if (!items.length) return null;

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {items.map((toast) => (
        <div
          key={toast.id}
          className={`px-4 py-2 rounded-lg border text-sm shadow-lg ${
            toast.type === "error"
              ? "bg-rose-500/20 border-rose-500/40 text-rose-100"
              : "bg-emerald-500/20 border-emerald-500/40 text-emerald-100"
          }`}
        >
          {toast.message}
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


function CitationBox({ citations }) {
  const [open, setOpen] = useState(false);

  if (!Array.isArray(citations) || citations.length === 0) return null;

  return (
    <div className="mt-4 rounded-xl border border-slate-700/80 bg-slate-900/50">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800/40"
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>Citations ({citations.length})</span>
        <span className="text-xs text-slate-400">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-slate-700/70 p-3">
          {citations.map((citation, idx) => {
            const documentName = citation?.document?.name || "Unknown document";
            const docId = citation?.document?.doc_id || "N/A";
            const page = citation?.location?.page_label || citation?.location?.page_physical || "N/A";
            const chapter = citation?.location?.chapter || "N/A";
            const section = citation?.location?.subheading || "N/A";
            const source = citation?.source || "N/A";
            const chunkId = citation?.chunk_id || "N/A";

            return (
              <div key={citation?.id || idx} className="rounded-lg border border-slate-700 bg-slate-950/40 p-3 text-xs text-slate-300">
                <div className="font-semibold text-emerald-300">{citation?.id || `CIT-${String(idx + 1).padStart(3, "0")}`}</div>
                <div className="mt-1">Document: {documentName}</div>
                <div>Doc ID: {docId}</div>
                <div>Page: {page}</div>
                <div>Chapter: {chapter}</div>
                <div>Section: {section}</div>
                <div>Chunk ID: {chunkId}</div>
                <div>Source: {source}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


function AuthPanel({ onAuthSuccess, addToast }) {
  const [mode, setMode] = useState("login");
  const [step, setStep] = useState("request");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    otp: "",
    newPassword: "",
  });
  const [devOtp, setDevOtp] = useState("");

  const title = useMemo(() => {
    if (mode === "register") return "Create account";
    if (mode === "forgot") return "Reset password";
    return "Welcome back";
  }, [mode]);

  const updateField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleLoginOrRegister = async (event) => {
    event.preventDefault();
    setLoading(true);

    try {
      if (!form.password.trim()) throw new Error("Password is required");
      if (mode === "register") {
        if (!form.username.trim() || !form.email.trim()) {
          throw new Error("Name, email, and password are required");
        }
        await registerUser({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          role: "user",
        });
      }

      const loginRes = await loginUser({
        email: form.email.trim(),
        username: form.username.trim(),
        password: form.password,
      });

      localStorage.setItem("access_token", loginRes.access_token);
      localStorage.setItem("refresh_token", loginRes.refresh_token || "");
      localStorage.setItem("role", loginRes.user?.role || "user");
      onAuthSuccess();
    } catch (error) {
      addToast(getErrorMessage(error, "Authentication failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleOtpRequest = async (event) => {
    event.preventDefault();
    setLoading(true);

    try {
      if (!form.email.trim()) throw new Error("Email is required");
      const res = await requestPasswordResetOtp(form.email.trim());
      setDevOtp(res.otp || "");
      setStep("verify");
      addToast(res.message || "OTP generated", "success");
      if (res.otp) {
        addToast(`Dev OTP: ${res.otp}`, "success");
      }
    } catch (error) {
      addToast(getErrorMessage(error, "Could not request OTP"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleOtpVerifyAndReset = async (event) => {
    event.preventDefault();
    setLoading(true);

    try {
      if (!form.email.trim() || !form.otp.trim() || !form.newPassword.trim()) {
        throw new Error("Email, OTP and new password are required");
      }
      await verifyPasswordResetOtp({
        email: form.email.trim(),
        otp: form.otp.trim(),
      });
      await resetPasswordWithOtp({
        email: form.email.trim(),
        otp: form.otp.trim(),
        new_password: form.newPassword,
      });

      addToast("Password updated. Sign in now.", "success");
      setMode("login");
      setStep("request");
      setDevOtp("");
      setForm((prev) => ({ ...prev, otp: "", newPassword: "", password: "" }));
    } catch (error) {
      addToast(getErrorMessage(error, "Password reset failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d141b] text-slate-100 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_8%_12%,rgba(16,185,129,.2),transparent_30%),radial-gradient(circle_at_86%_14%,rgba(56,189,248,.17),transparent_35%),radial-gradient(circle_at_80%_90%,rgba(249,115,22,.11),transparent_28%)]" />
      <div className="relative min-h-screen flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-md rounded-2xl border border-slate-700/70 bg-[#101922]/95 p-7 shadow-2xl backdrop-blur">
          <div className="text-xs uppercase tracking-[0.18em] text-emerald-300">Smart Medirag</div>
          <h1 className="mt-2 text-2xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-slate-400">Secure chat with role-based access.</p>

          {(mode === "login" || mode === "register") && (
            <form className="mt-6 space-y-4" onSubmit={handleLoginOrRegister}>
              <div>
                <label className="text-sm text-slate-300">Username</label>
                <input
                  type="text"
                  autoComplete="username"
                  value={form.username}
                  onChange={(e) => updateField("username", e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              {(mode === "register" || mode === "login") && (
                <div>
                  <label className="text-sm text-slate-300">Email</label>
                  <input
                    type="email"
                    autoComplete="email"
                    value={form.email}
                    onChange={(e) => updateField("email", e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                  />
                </div>
              )}
              <div>
                <label className="text-sm text-slate-300">Password</label>
                <input
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={form.password}
                  onChange={(e) => updateField("password", e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl bg-emerald-500 py-2.5 font-semibold text-slate-900 hover:bg-emerald-400 disabled:opacity-60"
              >
                {loading ? "Please wait..." : mode === "register" ? "Create account" : "Sign in"}
              </button>
            </form>
          )}

          {mode === "forgot" && step === "request" && (
            <form className="mt-6 space-y-4" onSubmit={handleOtpRequest}>
              <div>
                <label className="text-sm text-slate-300">Registered Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField("email", e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl bg-emerald-500 py-2.5 font-semibold text-slate-900 hover:bg-emerald-400 disabled:opacity-60"
              >
                {loading ? "Generating..." : "Generate OTP"}
              </button>
            </form>
          )}

          {mode === "forgot" && step === "verify" && (
            <form className="mt-6 space-y-4" onSubmit={handleOtpVerifyAndReset}>
              <div>
                <label className="text-sm text-slate-300">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField("email", e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              <div>
                <label className="text-sm text-slate-300">OTP</label>
                <input
                  type="text"
                  value={form.otp}
                  onChange={(e) => updateField("otp", e.target.value)}
                  placeholder={devOtp ? `Dev OTP: ${devOtp}` : "6-digit OTP"}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              <div>
                <label className="text-sm text-slate-300">New Password</label>
                <input
                  type="password"
                  value={form.newPassword}
                  onChange={(e) => updateField("newPassword", e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl bg-emerald-500 py-2.5 font-semibold text-slate-900 hover:bg-emerald-400 disabled:opacity-60"
              >
                {loading ? "Updating..." : "Verify OTP & Reset"}
              </button>
            </form>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate-400">
            <button className="hover:text-slate-100" onClick={() => { setMode("login"); setStep("request"); }}>
              Sign in
            </button>
            <button className="hover:text-slate-100" onClick={() => { setMode("register"); setStep("request"); }}>
              Register
            </button>
            <button className="hover:text-slate-100" onClick={() => { setMode("forgot"); setStep("request"); }}>
              Forgot password?
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


function ChatPanel({ onLogout, addToast, user }) {
  const [threads, setThreads] = useState([]);
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingAsk, setLoadingAsk] = useState(false);
  const bottomRef = useRef(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === threadId) || null,
    [threads, threadId]
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loadingAsk]);

  const loadThreads = async () => {
    try {
      setLoadingThreads(true);
      const data = await listThreads();
      setThreads(data);
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to load threads"), "error");
    } finally {
      setLoadingThreads(false);
    }
  };

  useEffect(() => {
    loadThreads();
  }, []);

  const openThread = async (id) => {
    try {
      setLoadingMessages(true);
      setThreadId(id);
      const data = await listThreadMessages(id);
      setMessages(data);
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to load messages"), "error");
    } finally {
      setLoadingMessages(false);
    }
  };

  const startNewChat = () => {
    setThreadId("");
    setMessages([]);
    setInput("");
  };

  const handleDeleteThread = async (id) => {
    if (!id) return;
    const ok = window.confirm("Delete this conversation permanently?");
    if (!ok) return;

    try {
      await deleteThread(id);
      if (threadId === id) {
        startNewChat();
      }
      await loadThreads();
      addToast("Conversation deleted", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Failed to delete conversation"), "error");
    }
  };

  const sendMessage = async () => {
    const query = input.trim();
    if (!query || loadingAsk) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoadingAsk(true);

    try {
      const res = await askQuestion({
        query,
        thread_id: threadId || null,
      });
      if (!threadId && res.thread_id) {
        setThreadId(res.thread_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response || "No response.",
          citations: Array.isArray(res.citations) ? res.citations : [],
        },
      ]);
      await loadThreads();
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: getErrorMessage(error, "Error generating response") },
      ]);
    } finally {
      setLoadingAsk(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#0b1015] text-slate-100">
      <aside className="hidden w-80 flex-col border-r border-slate-800 bg-[#101720] md:flex">
        <div className="border-b border-slate-800 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-emerald-300">Smart Medirag</div>
          <div className="mt-1 text-sm text-slate-400">Conversation history</div>
          <div className="mt-2 inline-flex rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-300">
            Role: {(user?.role || "user").toUpperCase()}
          </div>
        </div>
        <div className="p-4">
          <button
            onClick={startNewChat}
            className="w-full rounded-lg bg-emerald-500 px-3 py-2 font-semibold text-slate-900 hover:bg-emerald-400"
          >
            + New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4">
          {loadingThreads && (
            <div className="space-y-2 px-1">
              <div className="h-12 animate-pulse rounded-lg bg-slate-800/70" />
              <div className="h-12 animate-pulse rounded-lg bg-slate-800/70" />
              <div className="h-12 animate-pulse rounded-lg bg-slate-800/70" />
            </div>
          )}
          {!loadingThreads && threads.length === 0 && (
            <div className="px-2 text-sm text-slate-500">No conversations yet.</div>
          )}
          {!loadingThreads &&
            threads.map((thread) => (
              <div
                key={thread.id}
                className={`mb-2 w-full rounded-lg border px-3 py-2 text-left text-sm ${
                  threadId === thread.id
                    ? "border-emerald-500/70 bg-emerald-500/10"
                    : "border-slate-700 bg-slate-900/30"
                }`}
              >
                <button
                  onClick={() => openThread(thread.id)}
                  className="w-full text-left hover:bg-slate-800/40"
                >
                  <div className="truncate font-medium">{threadDisplayName(thread)}</div>
                  <div className="truncate text-xs text-slate-400">{thread.id}</div>
                  <div className="text-xs text-slate-400">{thread.message_count || 0} messages</div>
                </button>
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => handleDeleteThread(thread.id)}
                    className="rounded-md border border-rose-600/50 px-2 py-1 text-xs text-rose-300 hover:bg-rose-700/20"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
        </div>
        <div className="border-t border-slate-800 p-4">
          <button
            onClick={onLogout}
            className="w-full rounded-lg border border-slate-700 px-3 py-2 hover:bg-slate-800"
          >
            Logout
          </button>
        </div>
      </aside>

      <main className="flex min-h-screen flex-1 flex-col">
        <header className="border-b border-slate-800 bg-[#101720] px-4 py-3 md:hidden">
          <div className="flex items-center justify-between">
            <button className="rounded-lg border border-slate-700 px-2 py-1 text-sm" onClick={startNewChat}>
              New
            </button>
            <div className="max-w-[55%] truncate text-sm font-semibold">
              {activeThread ? threadDisplayName(activeThread) : "Smart Medirag Chat"}
            </div>
            <button className="rounded-lg border border-slate-700 px-2 py-1 text-sm" onClick={onLogout}>
              Logout
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-8 md:px-8">
            {messages.length === 0 && !loadingMessages && (
              <div className="py-16 text-center">
                <h1 className="text-3xl font-semibold">How can I help?</h1>
                <p className="mt-3 text-slate-400">Ask any medical question and continue your thread history.</p>
              </div>
            )}
            {loadingMessages && (
              <div className="space-y-3">
                <div className="h-20 animate-pulse rounded-2xl bg-slate-800/70" />
                <div className="h-20 animate-pulse rounded-2xl bg-slate-800/70" />
              </div>
            )}
            {messages.map((msg, index) => (
              <div key={`${msg.id || index}-${msg.role}`} className={msg.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={`w-full rounded-2xl border px-5 py-4 md:max-w-3xl ${
                    msg.role === "user"
                      ? "max-w-2xl border-emerald-500 bg-emerald-600 text-slate-900"
                      : "border-slate-800 bg-[#121922] text-slate-100"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <>
                      <div className="prose prose-invert max-w-none prose-pre:bg-slate-900 prose-code:text-emerald-300">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ""}</ReactMarkdown>
                      </div>
                      <CitationBox citations={msg.citations} />
                    </>
                  ) : (
                    <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                  )}
                </div>
              </div>
            ))}
            {loadingAsk && (
              <div className="w-full rounded-2xl border border-slate-800 bg-[#121922] px-5 py-4 text-slate-400 md:max-w-3xl">
                Thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="sticky bottom-0 border-t border-slate-800 bg-[#0b1015]/95 px-4 py-4 backdrop-blur md:px-8">
          <div className="mx-auto flex max-w-4xl items-end gap-3">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Smart Medirag..."
              className="flex-1 resize-none rounded-xl border border-slate-700 bg-[#121922] px-4 py-3 focus:outline-none focus:ring-2 focus:ring-emerald-500/60"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
            />
            <button
              onClick={sendMessage}
              disabled={loadingAsk}
              className="rounded-xl bg-emerald-500 px-5 py-3 font-semibold text-slate-900 hover:bg-emerald-400 disabled:opacity-60"
            >
              Send
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}


export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));
  const [user, setUser] = useState(null);
  const [toasts, setToasts] = useState([]);

  const addToast = (message, type = "success") => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 3500);
  };

  useEffect(() => {
    const handleUnauthorized = () => setToken(null);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  useEffect(() => {
    const loadCurrentUser = async () => {
      if (!token) {
        setUser(null);
        return;
      }
      try {
        const me = await getCurrentUser();
        setUser(me);
        if (me?.role) {
          localStorage.setItem("role", me.role);
        }
      } catch {
        setUser(null);
      }
    };
    loadCurrentUser();
  }, [token]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("role");
    setUser(null);
    setToken(null);
  };

  return (
    <>
      <Toasts items={toasts} />
      {!token ? (
        <AuthPanel onAuthSuccess={() => setToken(localStorage.getItem("access_token"))} addToast={addToast} />
      ) : (
        <ChatPanel onLogout={handleLogout} addToast={addToast} user={user} />
      )}
    </>
  );
}
