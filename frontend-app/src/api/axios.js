import axios from "axios";

/**
 * Shared axios client for API calls.
 * - Defaults to Vite proxy in dev (`/api`)
 * - Supports override with VITE_API_BASE_URL
 * - Attaches JWT automatically
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 120000,
});

const refreshClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 120000,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isUnauthorized = error.response?.status === 401;
    const isRefreshCall = originalRequest?.url?.includes("/auth/refresh");
    const hasRetried = originalRequest?._retry;

    if (isUnauthorized && !hasRetried && !isRefreshCall) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          originalRequest._retry = true;
          const refreshResponse = await refreshClient.post("/auth/refresh", {
            refresh_token: refreshToken,
          });
          const newAccessToken = refreshResponse.data?.access_token;
          if (newAccessToken) {
            localStorage.setItem("access_token", newAccessToken);
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
            return api(originalRequest);
          }
        } catch (_) {
          // fall through to logout below
        }
      }
    }

    if (isUnauthorized) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("role");
      window.dispatchEvent(new Event("auth:unauthorized"));
    }

    return Promise.reject(error);
  }
);

export default api;

