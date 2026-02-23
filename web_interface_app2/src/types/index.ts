export interface AuthState {
  username: string;
  apiKey: string;
  apiUrl: string;
}

export interface AuthContextType {
  auth: AuthState | null;
  isAuthenticated: boolean;
  login: (username: string, apiKey: string, apiUrl: string) => Promise<void>;
  logout: () => void;
}
