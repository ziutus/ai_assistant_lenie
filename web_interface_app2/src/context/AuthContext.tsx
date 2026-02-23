import React, { createContext, useCallback, useMemo, useState } from 'react';
import type { AuthContextType, AuthState } from '../types';
import { clearAuth, loadAuth, saveAuth } from '../services/storage';
import { validateApiKey } from '../services/api';

export const AuthContext = createContext<AuthContextType>({
  auth: null,
  isAuthenticated: false,
  login: async () => {},
  logout: () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [auth, setAuth] = useState<AuthState | null>(loadAuth);

  const login = useCallback(async (username: string, apiKey: string, apiUrl: string) => {
    await validateApiKey(apiUrl, apiKey);
    const state: AuthState = { username, apiKey, apiUrl };
    saveAuth(state);
    setAuth(state);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setAuth(null);
  }, []);

  const value = useMemo(
    () => ({ auth, isAuthenticated: auth !== null, login, logout }),
    [auth, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
