"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import type { User } from "@/types";
import { api } from "./api";
import {
  getToken,
  setToken,
  removeToken,
  getStoredUser,
  setStoredUser,
} from "./utils";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (phoneOrEmail: string, password: string) => Promise<void>;
  register: (
    phone: string,
    password: string,
    smsCode: string
  ) => Promise<void>;
  emailLogin: (email: string, password: string) => Promise<void>;
  emailRegister: (email: string, password: string, code: string) => Promise<void>;
  logout: () => void;
  refreshBalance: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  register: async () => {},
  emailLogin: async () => {},
  emailRegister: async () => {},
  logout: () => {},
  refreshBalance: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 页面加载时从 localStorage 恢复会话
  useEffect(() => {
    const restoreSession = async () => {
      const token = getToken();
      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        // 从 localStorage 恢复用户基本信息
        const stored = getStoredUser();
        if (stored) {
          const parsed = JSON.parse(stored) as User;
          setUser(parsed);
        }

        // 验证 token 有效性，同时获取最新余额
        const balance = await api.getBalance();
        setUser((prev) => {
          if (prev) {
            const updated = { ...prev, balanceFen: balance.amountFen };
            setStoredUser(JSON.stringify(updated));
            return updated;
          }
          return prev;
        });
      } catch {
        // token 无效，清除
        removeToken();
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    restoreSession();
  }, []);

  const login = useCallback(async (phone: string, password: string) => {
    const { access_token } = await api.login(phone, password);
    setToken(access_token);

    // 获取余额构造 user 对象（后端 /api/auth/login 只返回 token）
    const balance = await api.getBalance();
    const userData: User = {
      id: '', // 后端暂不返回 user id，用 phone 标识
      phone,
      balanceFen: balance.amountFen,
    };
    setStoredUser(JSON.stringify(userData));
    setUser(userData);
  }, []);

  const register = useCallback(
    async (phone: string, password: string, smsCode: string) => {
      await api.register(phone, password, smsCode);
    },
    []
  );

  const emailLogin = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.emailLogin(email, password);
    setToken(access_token);

    const balance = await api.getBalance();
    const userData: User = {
      id: '',
      phone: email,
      balanceFen: balance.amountFen,
    };
    setStoredUser(JSON.stringify(userData));
    setUser(userData);
  }, []);

  const emailRegister = useCallback(
    async (email: string, password: string, code: string) => {
      await api.emailRegister(email, password, code);
    },
    []
  );

  const logout = useCallback(() => {
    removeToken();
    setUser(null);
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  }, []);

  const refreshBalance = useCallback(async () => {
    try {
      const balance = await api.getBalance();
      setUser((prev) => {
        if (prev) {
          const updated = { ...prev, balanceFen: balance.amountFen };
          setStoredUser(JSON.stringify(updated));
          return updated;
        }
        return prev;
      });
    } catch {
      // 静默失败
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        emailLogin,
        emailRegister,
        logout,
        refreshBalance,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  return useContext(AuthContext);
}
