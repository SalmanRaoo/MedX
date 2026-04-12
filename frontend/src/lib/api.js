import axios from "axios";

const BASE_URL = "http://localhost:8000";
const AI_BASE_URL = "http://localhost:8001";

export const publicApi = axios.create({
  baseURL: BASE_URL,
});

export const api = axios.create({
  baseURL: BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("medx_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem("medx_token");
      localStorage.removeItem("medx_user");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);


export const aiApi = axios.create({
  baseURL: AI_BASE_URL,
});

