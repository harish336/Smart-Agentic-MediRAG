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
    const response = await api.post("/auth/forgot-password/request-otp", { email });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to send OTP" };
  }
};

export const resetPasswordWithOtp = async ({ email, otp, new_password }) => {
  try {
    const response = await api.post("/auth/forgot-password/reset", {
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
  localStorage.removeItem("role");
};

