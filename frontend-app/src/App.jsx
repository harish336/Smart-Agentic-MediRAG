import { useState } from "react";
import { Eye, EyeOff, Mail, Lock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

/* =============================
   GLOBAL STYLE FIX (Remove Edge default reveal icon)
============================= */

const GlobalStyles = () => (
  <style>{`
    input::-ms-reveal,
    input::-ms-clear {
      display: none;
    }
  `}</style>
);

/* =============================
   Premium Input Component
============================= */

function Input({ label, type, icon: Icon, value, onChange, error, isPassword }) {
  const [showPassword, setShowPassword] = useState(false);
  const inputType = isPassword && showPassword ? "text" : type;

  return (
    <div className="w-full">
      <label className="block text-sm font-medium text-gray-600 mb-2">
        {label}
      </label>

      <div className="relative group">
        {Icon && (
          <Icon
            size={18}
            className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-indigo-600 transition"
          />
        )}

        <input
          type={inputType}
          value={value}
          onChange={onChange}
          className={`w-full ${Icon ? "pl-12" : "pl-4"} pr-12 py-3 rounded-xl border border-gray-300 bg-white shadow-sm
            ${error ? "border-red-400" : "border-gray-300"}
            focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500
            transition duration-200`}
        />

        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-indigo-600 transition"
          >
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-500 mt-1">{error}</p>
      )}
    </div>
  );
}

/* =============================
   Login Component
============================= */

function Login({ switchToSignup, onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});

  const validate = () => {
    const newErrors = {};

    if (!email) newErrors.email = "Email is required";
    if (!password) newErrors.password = "Password is required";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (validate()) {
      onLogin();
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="bg-white p-10 rounded-2xl shadow-2xl w-full max-w-md"
    >
      <h2 className="text-3xl font-semibold text-center text-gray-800 mb-8">
        Medical Assistant
      </h2>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Input
          label="Email Address"
          type="email"
          icon={Mail}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />

        <Input
          label="Password"
          type="password"
          icon={Lock}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          isPassword
        />

        <button
          type="submit"
          className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-medium shadow-md hover:shadow-lg hover:scale-[1.02] transition duration-200"
        >
          Login
        </button>
      </form>

      <div className="text-center mt-5 text-sm">
        <button className="text-indigo-600 hover:underline">
          Forgot Password?
        </button>
      </div>

      <div className="text-center mt-4 text-sm">
        Don&apos;t have an account?{' '}
        <button
          onClick={switchToSignup}
          className="text-indigo-600 font-medium hover:underline"
        >
          Sign Up
        </button>
      </div>
    </motion.div>
  );
}

/* =============================
   Signup Component
============================= */

function Signup({ switchToLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState({});

  const validate = () => {
    const newErrors = {};

    if (!email) newErrors.email = "Email is required";
    if (!password) newErrors.password = "Password is required";
    if (!confirmPassword)
      newErrors.confirmPassword = "Confirm Password is required";
    if (password && confirmPassword && password !== confirmPassword)
      newErrors.confirmPassword = "Passwords do not match";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (validate()) {
      alert("Account created successfully");
      switchToLogin();
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="bg-white p-10 rounded-2xl shadow-2xl w-full max-w-md"
    >
      <h2 className="text-3xl font-semibold text-center text-gray-800 mb-8">
        Medical Assistant
      </h2>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Input
          label="Email Address"
          type="email"
          icon={Mail}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />

        <Input
          label="Password"
          type="password"
          icon={Lock}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          isPassword
        />

        <Input
          label="Confirm Password"
          type="password"
          icon={Lock}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          error={errors.confirmPassword}
          isPassword
        />

        <button
          type="submit"
          className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-medium shadow-md hover:shadow-lg hover:scale-[1.02] transition duration-200"
        >
          Sign Up
        </button>
      </form>

      <div className="text-center mt-5 text-sm">
        Already have an account?{' '}
        <button
          onClick={switchToLogin}
          className="text-indigo-600 font-medium hover:underline"
        >
          Login
        </button>
      </div>
    </motion.div>
  );
}

/* =============================
   Main Auth Layout (Professional Split Look)
============================= */

export default function AuthApp() {
  const [isLogin, setIsLogin] = useState(true);

  const handleLoginSuccess = () => {
    alert("Login successful - Ready for backend redirect");
  };

  return (
    <>
      <GlobalStyles />
      <div className="min-h-screen grid md:grid-cols-2 bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800">
        {/* Branding Panel */}
        <div className="hidden md:flex flex-col justify-center items-center text-white p-16">
          {/* Logo */}
          <img
            src="\logo.jpeg"
            alt="Medical Assistant Logo"
            className="w-56 h-auto mb-10 drop-shadow-2xl"
          />

          {/* Title */}
          <h1 className="text-3xl font-semibold tracking-wide text-white">
            Medical Assistant
          </h1>
        </div>

        {/* Form Panel */}
        <div className="flex items-center justify-center bg-gray-50 px-6 py-12">
          <AnimatePresence mode="wait">
            {isLogin ? (
              <Login
                key="login"
                switchToSignup={() => setIsLogin(false)}
                onLogin={handleLoginSuccess}
              />
            ) : (
              <Signup
                key="signup"
                switchToLogin={() => setIsLogin(true)}
              />
            )}
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}
