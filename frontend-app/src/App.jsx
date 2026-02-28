import { useEffect, useMemo, useRef, useState } from "react";
import { askQuestion } from "./api/answer";
import {
  loginUser,
  registerUser,
  requestPasswordResetOtp,
  resetPasswordWithOtp,
} from "./api/auth";

function formatWithCitations(text) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    if (part.match(/\[\d+\]/)) {
      return (
        <span
          key={index}
          className="text-emerald-300 font-semibold cursor-pointer hover:underline"
        >
          {part}
        </span>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function normalizeCitations(citations) {
  if (!citations) return [];

  const cleaned = citations.map((c) => ({
    book: c.document_name || "Unknown Document",
    chapter: c.chapter || null,
    subheading: c.subheading || null,
    page: c.page_physical || null,
  }));

  return [...new Map(cleaned.map((c) => [`${c.book}-${c.page}`, c])).values()];
}

function getErrorMessage(error, fallback) {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  return error.message || error.error || fallback;
}

function AuthPanel({ onAuthSuccess }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    otp: "",
    newPassword: "",
  });
  const [forgotStep, setForgotStep] = useState("request");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const clearFeedback = () => {
    setError("");
    setSuccess("");
  };

  const submitAuth = async (e) => {
    e.preventDefault();
    clearFeedback();

    if (!form.username.trim() || !form.password.trim()) {
      setError("Username and password are required.");
      return;
    }

    if (mode === "register" && !form.email.trim()) {
      setError("Email is required.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "register") {
        await registerUser({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          role: "user",
        });
      }

      const loginRes = await loginUser({
        username: form.username.trim(),
        password: form.password,
      });

      if (!loginRes?.access_token) {
        throw new Error("Login succeeded but no token was returned.");
      }

      localStorage.setItem("access_token", loginRes.access_token);
      localStorage.setItem("role", loginRes.role || "user");
      onAuthSuccess();
    } catch (err) {
      setError(getErrorMessage(err, "Authentication failed."));
    } finally {
      setLoading(false);
    }
  };

  const submitOtpRequest = async (e) => {
    e.preventDefault();
    clearFeedback();

    if (!form.email.trim()) {
      setError("Email is required.");
      return;
    }

    setLoading(true);
    try {
      const response = await requestPasswordResetOtp(form.email.trim());
      setSuccess(response.message || "If registered, OTP was sent.");
      setForgotStep("verify");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to send OTP."));
    } finally {
      setLoading(false);
    }
  };

  const submitOtpVerify = async (e) => {
    e.preventDefault();
    clearFeedback();

    if (!form.email.trim() || !form.otp.trim() || !form.newPassword.trim()) {
      setError("Email, OTP and new password are required.");
      return;
    }

    setLoading(true);
    try {
      const response = await resetPasswordWithOtp({
        email: form.email.trim(),
        otp: form.otp.trim(),
        new_password: form.newPassword,
      });
      setSuccess(response.message || "Password reset successful. Please sign in.");
      setMode("login");
      setForgotStep("request");
      setForm((prev) => ({ ...prev, otp: "", newPassword: "", password: "" }));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to reset password."));
    } finally {
      setLoading(false);
    }
  };

  const title = useMemo(() => {
    if (mode === "register") return "Create account";
    if (mode === "forgot") return "Reset password";
    return "Welcome back";
  }, [mode]);

  return (
    <div className="min-h-screen bg-[#0f1418] text-slate-100 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_10%_15%,rgba(16,185,129,.18),transparent_35%),radial-gradient(circle_at_82%_5%,rgba(59,130,246,.15),transparent_38%),radial-gradient(circle_at_65%_90%,rgba(234,179,8,.09),transparent_30%)]" />
      <div className="relative min-h-screen flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-md bg-[#10161d]/92 backdrop-blur-xl border border-slate-700/70 rounded-2xl shadow-2xl p-7">
          <div className="text-sm uppercase tracking-[0.18em] text-emerald-300">Smart Medirag</div>
          <h1 className="text-2xl font-semibold mt-2">{title}</h1>
          <p className="text-sm text-slate-400 mt-1">
            {mode === "forgot"
              ? "Verify OTP sent to your email and set a new password."
              : "Medical assistant with grounded references."}
          </p>

          {(mode === "login" || mode === "register") && (
            <form onSubmit={submitAuth} className="mt-6 space-y-4">
              <div>
                <label className="text-sm text-slate-300">Username</label>
                <input
                  type="text"
                  value={form.username}
                  onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
                  className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                  placeholder="Enter username"
                  autoComplete="username"
                />
              </div>

              {mode === "register" && (
                <div>
                  <label className="text-sm text-slate-300">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                    className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                    placeholder="Enter email"
                    autoComplete="email"
                  />
                </div>
              )}

              <div>
                <label className="text-sm text-slate-300">Password</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
                  className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                  placeholder="Enter password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
              </div>

              {error && (
                <div className="text-sm text-rose-200 bg-rose-500/20 border border-rose-500/40 rounded-lg px-3 py-2">
                  {error}
                </div>
              )}
              {success && (
                <div className="text-sm text-emerald-100 bg-emerald-500/20 border border-emerald-500/40 rounded-lg px-3 py-2">
                  {success}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-xl bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400 disabled:opacity-60"
              >
                {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>
          )}

          {mode === "forgot" && (
            <>
              {forgotStep === "request" && (
                <form onSubmit={submitOtpRequest} className="mt-6 space-y-4">
                  <div>
                    <label className="text-sm text-slate-300">Registered Email</label>
                    <input
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                      className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                      placeholder="name@example.com"
                    />
                  </div>

                  {error && (
                    <div className="text-sm text-rose-200 bg-rose-500/20 border border-rose-500/40 rounded-lg px-3 py-2">
                      {error}
                    </div>
                  )}
                  {success && (
                    <div className="text-sm text-emerald-100 bg-emerald-500/20 border border-emerald-500/40 rounded-lg px-3 py-2">
                      {success}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 rounded-xl bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400 disabled:opacity-60"
                  >
                    {loading ? "Sending..." : "Send OTP"}
                  </button>
                </form>
              )}

              {forgotStep === "verify" && (
                <form onSubmit={submitOtpVerify} className="mt-6 space-y-4">
                  <div>
                    <label className="text-sm text-slate-300">Email</label>
                    <input
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                      className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-slate-300">OTP</label>
                    <input
                      type="text"
                      value={form.otp}
                      onChange={(e) => setForm((prev) => ({ ...prev, otp: e.target.value }))}
                      className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                      placeholder="6-digit OTP"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-slate-300">New Password</label>
                    <input
                      type="password"
                      value={form.newPassword}
                      onChange={(e) => setForm((prev) => ({ ...prev, newPassword: e.target.value }))}
                      className="mt-1 w-full px-3 py-2.5 bg-slate-900/70 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400/70"
                      placeholder="At least 6 characters"
                    />
                  </div>

                  {error && (
                    <div className="text-sm text-rose-200 bg-rose-500/20 border border-rose-500/40 rounded-lg px-3 py-2">
                      {error}
                    </div>
                  )}
                  {success && (
                    <div className="text-sm text-emerald-100 bg-emerald-500/20 border border-emerald-500/40 rounded-lg px-3 py-2">
                      {success}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 rounded-xl bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400 disabled:opacity-60"
                  >
                    {loading ? "Updating..." : "Verify OTP & Reset"}
                  </button>
                </form>
              )}
            </>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate-400">
            <button
              className="hover:text-slate-100"
              onClick={() => {
                setMode("login");
                setForgotStep("request");
                clearFeedback();
              }}
            >
              Sign in
            </button>
            <button
              className="hover:text-slate-100"
              onClick={() => {
                setMode("register");
                setForgotStep("request");
                clearFeedback();
              }}
            >
              Register
            </button>
            <button
              className="hover:text-slate-100"
              onClick={() => {
                setMode("forgot");
                setForgotStep("request");
                clearFeedback();
              }}
            >
              Forgot password?
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatPanel({ onLogout }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openCitationsIndex, setOpenCitationsIndex] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleAsk = async () => {
    if (!input.trim() || loading) return;

    const question = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setLoading(true);

    try {
      const data = await askQuestion({
        query: question,
        thread_id: threadId,
      });

      if (data.thread_id) setThreadId(data.thread_id);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.response || "No response received.",
          citations: normalizeCitations(data.citations || []),
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: getErrorMessage(error, "Error fetching response."),
          citations: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setThreadId(null);
    setInput("");
  };

  return (
    <div className="min-h-screen bg-[#0b1015] text-slate-100 flex">
      <aside className="hidden md:flex md:w-72 flex-col border-r border-slate-800 bg-[#111820]">
        <div className="p-4 border-b border-slate-800">
          <div className="text-xs uppercase tracking-[0.15em] text-emerald-300">Smart Medirag</div>
          <div className="text-sm text-slate-400 mt-1">Clinical AI Workspace</div>
        </div>
        <div className="p-4">
          <button
            onClick={startNewChat}
            className="w-full px-3 py-2 rounded-lg bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400"
          >
            + New Chat
          </button>
        </div>
        <div className="px-4 text-xs text-slate-500">
          Answers include source citations when available.
        </div>
        <div className="mt-auto p-4 border-t border-slate-800">
          <button
            onClick={onLogout}
            className="w-full px-3 py-2 rounded-lg border border-slate-700 hover:bg-slate-800"
          >
            Logout
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-h-screen">
        <header className="md:hidden border-b border-slate-800 px-4 py-3 flex items-center justify-between bg-[#111820]">
          <div className="text-sm font-semibold">Smart Medirag Chat</div>
          <button
            onClick={onLogout}
            className="px-3 py-1.5 rounded-lg border border-slate-700 text-sm"
          >
            Logout
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto w-full px-4 py-8 md:px-8 space-y-6">
            {messages.length === 0 && (
              <div className="text-center py-16">
                <h1 className="text-3xl font-semibold text-slate-100">How can I help?</h1>
                <p className="text-slate-400 mt-3">
                  Ask any medical question and I will return evidence-backed responses.
                </p>
              </div>
            )}

            {messages.map((msg, index) => (
              <div key={index} className={msg.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={`w-full md:max-w-3xl rounded-2xl px-5 py-4 border ${msg.role === "user"
                      ? "bg-emerald-600 text-slate-900 border-emerald-500 max-w-2xl"
                      : "bg-[#121922] border-slate-800 text-slate-100"
                    }`}
                >
                  <div className="whitespace-pre-line leading-relaxed">
                    {msg.role === "assistant" ? formatWithCitations(msg.content) : msg.content}
                  </div>

                  {msg.role === "assistant" &&
                    msg.citations &&
                    msg.citations.length > 0 && (
                      <div className="mt-4 text-sm">
                        <button
                          onClick={() =>
                            setOpenCitationsIndex(
                              openCitationsIndex === index ? null : index
                            )
                          }
                          className="text-emerald-300 hover:underline font-medium"
                        >
                          {openCitationsIndex === index
                            ? "Hide Citations"
                            : `View Citations (${msg.citations.length})`}
                        </button>

                        {openCitationsIndex === index && (
                          <div className="mt-3 pt-3 border-t border-slate-700 space-y-2">
                            <div className="font-semibold text-slate-200 mb-2">
                              Citations
                            </div>

                            {msg.citations.map((c, i) => (
                              <div
                                key={i}
                                className="bg-slate-900/40 rounded-lg border border-slate-700 p-3"
                              >
                                <div className="font-semibold text-slate-100">
                                  {c.book?.replace(".pdf", "")}
                                </div>

                                {c.chapter && (
                                  <div className="text-slate-400">
                                    Chapter: {c.chapter}
                                  </div>
                                )}

                                {c.subheading && (
                                  <div className="text-slate-400 italic">
                                    {c.subheading}
                                  </div>
                                )}

                                {c.page && (
                                  <div className="text-emerald-300 font-medium">
                                    Page {c.page}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="w-full md:max-w-3xl rounded-2xl px-5 py-4 border border-slate-800 bg-[#121922] text-slate-400">
                Thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="sticky bottom-0 border-t border-slate-800 bg-[#0b1015]/95 backdrop-blur px-4 py-4 md:px-8">
          <div className="max-w-4xl mx-auto flex gap-3 items-end">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Smart Medirag..."
              className="flex-1 resize-none px-4 py-3 rounded-xl border border-slate-700 bg-[#121922] focus:outline-none focus:ring-2 focus:ring-emerald-500/60"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleAsk();
                }
              }}
            />
            <button
              onClick={handleAsk}
              disabled={loading}
              className="px-5 py-3 rounded-xl bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400 disabled:opacity-60"
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

  useEffect(() => {
    const handleUnauthorized = () => setToken(null);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("role");
    setToken(null);
  };

  if (!token) {
    return <AuthPanel onAuthSuccess={() => setToken(localStorage.getItem("access_token"))} />;
  }

  return <ChatPanel onLogout={handleLogout} />;
}

