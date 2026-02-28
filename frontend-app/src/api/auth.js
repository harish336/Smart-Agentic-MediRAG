import api from "./axios";

export const registerUser = async (data) => {
  try {
    const response = await api.post("/auth/register", {
      username: data.username,
      email: data.email,
      password: data.password,
      role: data.role || "user",
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Registration failed" };
  }
};

export const loginUser = async (credentials) => {
  try {
    const response = await api.post("/auth/login", {
      email: credentials.email,
      username: credentials.username,
      password: credentials.password,
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Login failed" };
  }
};

export const requestPasswordResetOtp = async (email) => {
  try {
    const response = await api.post("/auth/forgot-password", { email });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to send OTP" };
  }
};

export const verifyPasswordResetOtp = async ({ email, otp }) => {
  try {
    const response = await api.post("/auth/verify-otp", { email, otp });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Invalid OTP" };
  }
};

export const resetPasswordWithOtp = async ({ email, otp, new_password }) => {
  try {
    const response = await api.post("/auth/reset-password", {
      email,
      otp,
      new_password,
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to reset password" };
  }
};

export const logoutUser = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("role");
};

export const getCurrentUser = async () => {
  try {
    const response = await api.get("/auth/me");
    return response.data?.user || null;
  } catch (error) {
    throw error.response?.data || { error: "Failed to load current user" };
  }
};

